import logging
import os
import subprocess
import tempfile

from constants.stickers import WaStickers

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 60  # secondes, limite de securite pour le subprocess
LOTTIE_TIMEOUT = 90  # secondes, limite de securite pour lottie_convert.py (rendu Lottie -> webp)


class ConversionError(Exception):
    pass


def _run_ffmpeg(args):
    logger.debug('running ffmpeg: %s', ' '.join(args))
    result = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=FFMPEG_TIMEOUT
    )
    if result.returncode != 0:
        logger.error('ffmpeg error: %s', result.stderr.decode(errors='ignore'))
        raise ConversionError('ffmpeg failed with code {}'.format(result.returncode))


def convert_image_to_webp(input_path: str, output_tempfile):
    """convertit une photo (jpg/png/...) en sticker statique webp 512x512"""
    with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp_out:
        output_path = tmp_out.name

    try:
        _run_ffmpeg([
            'ffmpeg', '-y', '-i', input_path,
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,'
                   'pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
            '-vcodec', 'libwebp',
            '-lossless', '0',
            '-q:v', '90',
            '-preset', 'picture',
            output_path
        ])

        with open(output_path, 'rb') as f:
            output_tempfile.write(f.read())
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def convert_video_to_webm(input_path: str, output_tempfile):
    """convertit une video/gif en sticker video conforme a Telegram
    (webm, vp9, <= 3 secondes, 512x512, sans audio)"""
    with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp_out:
        output_path = tmp_out.name

    try:
        _run_ffmpeg([
            'ffmpeg', '-y', '-i', input_path,
            '-t', '3',  # Telegram: sticker video max 3 secondes
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,'
                   'pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000,fps=30',
            '-c:v', 'libvpx-vp9',
            '-b:v', '256k',
            '-crf', '30',
            '-an',  # pas d'audio, obligatoire pour Telegram
            output_path
        ])

        with open(output_path, 'rb') as f:
            output_tempfile.write(f.read())
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


# ---------------------------------------------------------------------------
# Conversion Telegram -> WhatsApp (.wastickers)
# ---------------------------------------------------------------------------

# qualites testees dans l'ordre pour les stickers statiques, jusqu'a passer
# sous WaStickers.STATIC_MAX_BYTES
_WA_STATIC_QUALITIES = (90, 80, 70, 60, 50, 40, 30, 20)

# presets testes dans l'ordre pour les stickers animes/video (du meilleur au
# plus compresse). WhatsApp rejette TOUT le pack si un seul sticker anime
# depasse ~500KB, donc on reduit la duree/fps/qualite jusqu'a rentrer dedans.
_WA_ANIMATED_PRESETS = (
    {'duration': 3, 'fps': 15, 'q': 60},
    {'duration': 2.5, 'fps': 12, 'q': 45},
    {'duration': 2.5, 'fps': 10, 'q': 32},
    {'duration': 2, 'fps': 10, 'q': 22},
    {'duration': 2, 'fps': 8, 'q': 15},
    {'duration': 1.5, 'fps': 8, 'q': 10},
)


def convert_image_to_wa_static_webp(input_path: str, output_tempfile, max_bytes: int = WaStickers.STATIC_MAX_BYTES):
    """convertit une image statique (webp/png/jpg) en sticker statique WhatsApp:
    webp carre 512x512, en reduisant la qualite jusqu'a rentrer sous `max_bytes`"""

    last_data = None

    for quality in _WA_STATIC_QUALITIES:
        with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp_out:
            output_path = tmp_out.name

        try:
            _run_ffmpeg([
                'ffmpeg', '-y', '-i', input_path,
                '-vf', 'scale={0}:{0}:force_original_aspect_ratio=decrease,'
                       'pad={0}:{0}:(ow-iw)/2:(oh-ih)/2:color=0x00000000'.format(WaStickers.STICKER_SIZE),
                '-vcodec', 'libwebp',
                '-lossless', '0',
                '-q:v', str(quality),
                '-preset', 'picture',
                output_path
            ])

            with open(output_path, 'rb') as f:
                data = f.read()
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

        if not data:
            continue

        last_data = data
        if len(data) <= max_bytes:
            break

    if not last_data:
        raise ConversionError('ffmpeg a produit un fichier vide (conversion webp statique)')

    output_tempfile.write(last_data)
    output_tempfile.seek(0)


def convert_video_to_wa_animated_webp(input_path: str, output_tempfile, max_bytes: int = WaStickers.ANIMATED_MAX_BYTES):
    """convertit une video (webm/mp4/gif...) en sticker anime WhatsApp:
    webp anime 512x512, en reduisant duree/fps/qualite jusqu'a rentrer sous `max_bytes`"""

    last_data = None

    for preset in _WA_ANIMATED_PRESETS:
        with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp_out:
            output_path = tmp_out.name

        vf = (
            'fps={fps},scale={size}:{size}:force_original_aspect_ratio=decrease,'
            'pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:color=0x00000000'
        ).format(fps=preset['fps'], size=WaStickers.STICKER_SIZE)

        try:
            _run_ffmpeg([
                'ffmpeg', '-y', '-i', input_path,
                '-t', str(preset['duration']),
                '-vf', vf,
                '-vcodec', 'libwebp',
                '-lossless', '0',
                '-q:v', str(preset['q']),
                '-loop', '0',
                '-preset', 'picture',
                '-an', '-vsync', '0',
                output_path
            ])

            with open(output_path, 'rb') as f:
                data = f.read()
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

        if not data:
            continue

        last_data = data
        if len(data) <= max_bytes:
            break

    if not last_data:
        raise ConversionError('ffmpeg a produit un fichier vide (conversion webp anime)')

    output_tempfile.write(last_data)
    output_tempfile.seek(0)


def convert_tgs_to_wa_animated_webp(input_path: str, output_tempfile, max_bytes: int = WaStickers.ANIMATED_MAX_BYTES):
    """convertit un sticker anime Telegram (.tgs, Lottie gzippe) en webp anime WhatsApp.

    Necessite le paquet optionnel `lottie` (pip install "lottie[GIF]"), qui fournit
    le script `lottie_convert.py` utilise ici en subprocess (comme ffmpeg).
    Leve ConversionError si le script n'est pas installe ou si la conversion echoue:
    dans ce cas l'appelant doit "sauter" ce sticker (comme /export le fait deja pour
    les stickers en erreur) plutot que de faire echouer tout le pack.
    """

    with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp_out:
        output_path = tmp_out.name

    try:
        result = subprocess.run(
            [
                'lottie_convert.py',
                input_path,
                output_path,
                '--width', str(WaStickers.STICKER_SIZE),
                '--height', str(WaStickers.STICKER_SIZE),
                '--webp-quality', '70',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=LOTTIE_TIMEOUT
        )
        if result.returncode != 0 or not os.path.exists(output_path):
            logger.error('lottie_convert.py error: %s', result.stderr.decode(errors='ignore'))
            raise ConversionError('lottie_convert.py failed with code {}'.format(result.returncode))

        with open(output_path, 'rb') as f:
            data = f.read()

        if not data:
            raise ConversionError('lottie_convert.py a produit un fichier vide')

        if len(data) > max_bytes:
            logger.warning('tgs->webp sticker exceeds %d bytes (%d), sending anyway', max_bytes, len(data))

        output_tempfile.write(data)
        output_tempfile.seek(0)
    except FileNotFoundError as e:
        raise ConversionError(
            "le paquet 'lottie' n'est pas installe (pip install \"lottie[GIF]\"), "
            "impossible de convertir les stickers animes .tgs"
        ) from e
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
