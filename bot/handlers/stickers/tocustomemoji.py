import logging

# noinspection PyPackageRequirements
from telegram import ChatAction, Update
# noinspection PyPackageRequirements
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    Filters
)

from bot import stickersbot
from bot.stickers import StickerFile
from bot.strings import Strings
from ..conversation_statuses import Status
from ..fallback_commands import cancel_command, on_timeout
from ...customfilters import CustomFilters
from ...utils import decorators
from ...utils import image
from ...utils import utils

# noinspection PyPackageRequirements

logger = logging.getLogger(__name__)


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_toemoji_command(update: Update, context: CallbackContext):
    logger.info('/toemoji')

    options = {
        "-c": ("crop", "<code>crop transparent border areas</code>"),
        "-r": ("ignore_rateo", "<code>do not preserve the image's aspect rateo</code>")
    }

    enabled_options_description = utils.check_flags(options, context, pop_existing_flags=True)

    update.message.reply_text(Strings.TO_EMOJI_WAITING_STICKER)
    if enabled_options_description:
        update.message.reply_html(f"{Strings.ENABLED_FLAGS}{' + '.join(enabled_options_description)}")

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_sticker_received(update: Update, context: CallbackContext):
    logger.info('/toemoji: sticker received')

    sticker_file = StickerFile(message=update.message)
    sticker_file.download()

    im = image.File(sticker_file.sticker_tempfile, image.Options(max_size=100, square=True))
    im.options.crop_transparent_areas = "crop" in context.user_data
    im.options.keep_aspect_rateo = not ("ignore_rateo" in context.user_data)
    im.process()

    update.message.reply_document(
        im.result_tempfile,
        filename=f"{sticker_file.file_name()}",
        caption=sticker_file.get_emojis_str(),
        disable_content_type_detection=True
    )

    im.close()

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_sticker_unexpected_message(update: Update, context: CallbackContext):
    logger.info('/toemoji: unexpected message')

    update.message.reply_html(Strings.TO_EMOJI_UNEXPECTED_MESSAGE)

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_sticker_non_static_sticker(update: Update, context: CallbackContext):
    logger.info('/toemoji: non-static sticker')

    update.message.reply_html(Strings.TO_EMOJI_NON_STATIC_STICKER)

    return Status.WAITING_STICKER


stickersbot.add_handler(ConversationHandler(
    name='toemoji_command',
    persistent=False,
    entry_points=[CommandHandler(['toemoji', 'tocustomemoji', 'te'], on_toemoji_command)],
    states={
        Status.WAITING_STICKER: [
            CommandHandler(['toemoji', 'tocustomemoji', 'te'], on_toemoji_command),
            MessageHandler(CustomFilters.static_sticker, on_sticker_received),
            MessageHandler(CustomFilters.animated_sticker | CustomFilters.video_sticker, on_waiting_sticker_non_static_sticker),
            MessageHandler(Filters.all & ~CustomFilters.done_or_cancel, on_waiting_sticker_unexpected_message),
        ],
        ConversationHandler.TIMEOUT: [MessageHandler(Filters.all, on_timeout)]
    },
    fallbacks=[CommandHandler(['cancel', 'c', 'done', 'd'], cancel_command)],
    conversation_timeout=15 * 60
))
