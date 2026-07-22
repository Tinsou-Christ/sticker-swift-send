import json
import logging
import os
import tempfile
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import escape as html_escape
from types import SimpleNamespace

# noinspection PyPackageRequirements
from telegram import ChatAction, Update
# noinspection PyPackageRequirements
from telegram.error import BadRequest, TelegramError
# noinspection PyPackageRequirements
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    Filters,
)

from bot import stickersbot
from bot.strings import Strings
from constants.stickers import WaStickers
from ..conversation_statuses import Status
from ..fallback_commands import cancel_command
from ...utils import decorators
from ...utils import converter
from ...utils import wastickers

logger = logging.getLogger(__name__)

# Nombre de workers pour download + conversion en parallele.
# 8 est un bon compromis: on sature la bande passante Telegram sans se faire
# rate-limiter, et Pillow/ffmpeg/lottie liberent le GIL pendant leur travail.
DOWNLOAD_WORKERS = 8
CONVERT_WORKERS = 8


def _get_sticker_set_raw(context: CallbackContext, name: str) -> SimpleNamespace:
    """Voir version d'origine: contourne le bug PTB 13.x sur getStickerSet."""

    url = 'https://api.telegram.org/bot{}/getStickerSet?{}'.format(
        context.bot.token, urllib.parse.urlencode({'name': name})
    )

    with urllib.request.urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode('utf-8'))

    if not payload.get('ok'):
        raise RuntimeError(payload.get('description', 'getStickerSet failed'))

    result = payload['result']

    stickers = [
        SimpleNamespace(
            file_id=s['file_id'],
            file_unique_id=s.get('file_unique_id'),
            is_animated=bool(s.get('is_animated', False)),
            is_video=bool(s.get('is_video', False)),
            emoji=s.get('emoji'),
        )
        for s in result.get('stickers', [])
    ]

    return SimpleNamespace(name=result['name'], title=result['title'], stickers=stickers)


def _download_and_convert(context: CallbackContext, sticker) -> bytes:
    """Telecharge un sticker puis le convertit en webp WhatsApp. Renvoie les
    bytes du webp. Leve une exception si ca echoue: l'appelant skip."""

    if sticker.is_animated:
        suffix = '.tgs'
    elif sticker.is_video:
        suffix = '.webm'
    else:
        suffix = '.webp'

    input_path = None
    out = tempfile.SpooledTemporaryFile()
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
            input_path = tmp_in.name

        telegram_file = context.bot.get_file(sticker.file_id)
        telegram_file.download(custom_path=input_path)

        if sticker.is_animated:
            converter.convert_tgs_to_wa_animated_webp(input_path, out)
        elif sticker.is_video:
            converter.convert_video_to_wa_animated_webp(input_path, out)
        else:
            converter.convert_image_to_wa_static_webp(input_path, out)

        out.seek(0)
        return out.read()
    finally:
        out.close()
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except OSError:
                pass


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_import_command(update: Update, _):
    logger.info('/import')

    update.message.reply_text(Strings.IMPORT_PACK_SELECT)

    return Status.IMPORT_WAITING_STICKER


@decorators.action(ChatAction.UPLOAD_DOCUMENT)
@decorators.failwithmessage
@decorators.logconversation
def on_sticker_receive(update: Update, context: CallbackContext):
    """Import Telegram -> WhatsApp en mode STREAMING + PARALLELE.

    - Telecharge et convertit les stickers en parallele (ThreadPoolExecutor).
    - Des qu'un batch de STICKERS_PER_FILE (=30) stickers consecutifs est pret,
      on construit le .wastickers et on l'envoie IMMEDIATEMENT, sans attendre
      les autres. Le 1er fichier arrive donc en quelques secondes au lieu
      d'attendre la fin de tout le pack.
    """

    logger.info('user sent a sticker from the pack to import (fast import)')

    if not update.message.sticker.set_name:
        update.message.reply_text(Strings.IMPORT_PACK_NO_PACK)
        return Status.IMPORT_WAITING_STICKER

    sticker_set = _get_sticker_set_raw(context, update.message.sticker.set_name)
    total = len(sticker_set.stickers)
    if total == 0:
        update.message.reply_text(Strings.IMPORT_PACK_NO_STICKERS_CONVERTED)
        return ConversationHandler.END

    files_count = wastickers.files_count_for(total)

    # Un seul message court avant de commencer, pour ne pas retarder le 1er fichier.
    update.message.reply_html(
        Strings.IMPORT_PACK_DETAILS.format(html_escape(sticker_set.title), total, files_count)
    )

    batch_size = WaStickers.STICKERS_PER_FILE
    safe_title = sticker_set.title or 'Imported Pack'
    author = f'@{context.bot.username}'

    # Slots ordonnes: converted[i] sera None (echec) ou bytes.
    converted = [None] * total
    done_flags = [False] * total
    lock = threading.Lock()
    next_batch_to_send = [0]  # mutable pour closure
    skipped = [0]
    tray_icon = [None]  # calcule une seule fois a partir du 1er sticker converti

    send_pool = ThreadPoolExecutor(max_workers=2)  # 2 uploads en parallele
    send_futures = []

    def _try_flush_batches():
        """Envoie tous les batches consecutifs deja complets, dans l'ordre."""
        while True:
            with lock:
                b = next_batch_to_send[0]
                start = b * batch_size
                if start >= total:
                    return
                end = min(start + batch_size, total)
                # batch pret si tous les slots [start:end] sont "done"
                if not all(done_flags[start:end]):
                    return
                batch_bytes = [converted[i] for i in range(start, end) if converted[i] is not None]
                next_batch_to_send[0] = b + 1

            if not batch_bytes:
                continue  # tout le batch a echoue, on passe au suivant

            # Tray icon: construite une seule fois a partir du 1er webp disponible.
            if tray_icon[0] is None:
                try:
                    tray_icon[0] = wastickers.build_tray_icon_png(batch_bytes[0])
                except Exception:
                    logger.exception('tray icon build failed, using first sticker webp raw is not possible; skipping tray fallback')
                    tray_icon[0] = wastickers.build_tray_icon_png(batch_bytes[0])

            files = wastickers.build_wastickers_files(
                title=safe_title,
                author=author,
                stickers_webp=batch_bytes,
                tray_icon_png=tray_icon[0],
                batch_size=batch_size,
            )
            # build_wastickers_files renvoie ici 1 seul fichier (batch <= batch_size),
            # mais on itere par securite.
            for filename, buf in files:
                # renomme pour refleter la position du batch dans le pack complet
                part_index = (start // batch_size) + 1
                if files_count > 1:
                    base = filename.rsplit('.', 1)[0]
                    filename = f'{base}_{part_index}of{files_count}.wastickers'
                send_futures.append(
                    send_pool.submit(_send_document_safe, update, filename, buf)
                )

    def _mark_done(index: int, data):
        with lock:
            converted[index] = data
            done_flags[index] = True
            if data is None:
                skipped[0] += 1
        _try_flush_batches()

    # Lance downloads+conversions en parallele. Chaque sticker est un job.
    with ThreadPoolExecutor(max_workers=max(DOWNLOAD_WORKERS, CONVERT_WORKERS)) as pool:
        futures = {}
        for idx, sticker in enumerate(sticker_set.stickers):
            fut = pool.submit(_download_and_convert, context, sticker)
            futures[fut] = idx

        for fut in futures:
            idx = futures[fut]
            try:
                data = fut.result()
                _mark_done(idx, data)
            except Exception:
                logger.warning('skipping sticker #%d of %s', idx, sticker_set.name, exc_info=True)
                _mark_done(idx, None)

    # Attend la fin des uploads
    for f in send_futures:
        try:
            f.result()
        except Exception:
            logger.exception('send failed')
    send_pool.shutdown(wait=True)

    if skipped[0] >= total:
        update.message.reply_text(Strings.IMPORT_PACK_NO_STICKERS_CONVERTED)
        return ConversationHandler.END

    complete_text = Strings.IMPORT_PACK_COMPLETE.format(files_count)
    if skipped[0]:
        complete_text += Strings.IMPORT_PACK_SKIPPED_STICKERS.format(skipped[0])
    update.message.reply_text(complete_text)

    return ConversationHandler.END


def _send_document_safe(update: Update, filename: str, buf):
    try:
        update.message.reply_document(buf, filename=filename)
    except (TelegramError, BadRequest) as e:
        logger.error('error while sending a .wastickers file (%s): %s', filename, str(e))


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_ongoing_async_operation(update: Update, _):
    logger.info('user sent a message while the import is ongoing')
    update.message.reply_text(Strings.IMPORT_ONGOING)


stickersbot.add_handler(ConversationHandler(
    name='import_command',
    persistent=False,
    entry_points=[CommandHandler(['import', 'towa', 'importpack'], on_import_command)],
    states={
        Status.IMPORT_WAITING_STICKER: [
            MessageHandler(Filters.sticker, on_sticker_receive, run_async=True),
        ],
        ConversationHandler.WAITING: [MessageHandler(Filters.all, on_ongoing_async_operation)]
    },
    fallbacks=[CommandHandler(['cancel', 'c', 'done', 'd'], cancel_command)],
))
