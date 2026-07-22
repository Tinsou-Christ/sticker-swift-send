import logging
import math
import zipfile
from io import BytesIO
from typing import List, Tuple

from PIL import Image

from constants.stickers import WaStickers

logger = logging.getLogger(__name__)


def build_tray_icon_png(first_sticker_webp: bytes) -> bytes:
    """construit l'icone du tray (96x96 PNG) requise par WhatsApp a partir
    du 1er sticker du pack DEJA CONVERTI en webp (statique ou anime: PIL prend
    automatiquement la 1ere frame d'un webp anime)"""

    im = Image.open(BytesIO(first_sticker_webp)).convert('RGBA')

    size = WaStickers.TRAY_ICON_SIZE
    canvas = Image.new('RGBA', (size, size), (255, 255, 255, 255))  # fond blanc opaque

    scale = min(size / im.width, size / im.height)
    new_w, new_h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    im = im.resize((new_w, new_h), Image.LANCZOS)

    x = (size - new_w) // 2
    y = (size - new_h) // 2
    canvas.paste(im, (x, y), im)

    buf = BytesIO()
    canvas.save(buf, 'PNG', optimize=True)
    data = buf.getvalue()

    if len(data) > WaStickers.TRAY_ICON_MAX_BYTES:
        # re-encode avec une palette reduite si l'icone est trop lourde (rare)
        buf = BytesIO()
        canvas.convert('P', palette=Image.ADAPTIVE, colors=128).save(buf, 'PNG', optimize=True)
        data = buf.getvalue()

    return data


def chunk_list(items: list, size: int) -> List[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_wastickers_files(
    title: str,
    author: str,
    stickers_webp: List[bytes],
    tray_icon_png: bytes,
    batch_size: int = WaStickers.STICKERS_PER_FILE,
) -> List[Tuple[str, BytesIO]]:
    """decoupe la liste de stickers deja convertis (bytes webp) en plusieurs
    fichiers .wastickers de `batch_size` stickers max chacun.

    renvoie une liste de tuples (filename, BytesIO) prets a etre envoyes"""

    if not stickers_webp:
        raise ValueError('no stickers to pack')

    batches = chunk_list(stickers_webp, batch_size)
    total_files = len(batches)

    safe_title = (title or 'Imported Pack').strip()[:WaStickers.TITLE_MAX_LEN] or 'Imported Pack'
    safe_author = (author or 'sticker-thief').strip()[:WaStickers.AUTHOR_MAX_LEN] or 'sticker-thief'

    results = []

    for part_index, batch in enumerate(batches, start=1):
        buf = BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            # si un seul fichier au total, pas besoin de suffixe " (1/1)"
            part_title = safe_title if total_files == 1 else f'{safe_title} ({part_index}/{total_files})'
            zf.writestr('title.txt', part_title[:WaStickers.TITLE_MAX_LEN])
            zf.writestr('author.txt', safe_author)
            zf.writestr('icon.png', tray_icon_png)

            for i, webp_bytes in enumerate(batch, start=1):
                zf.writestr(f'{i:02d}.webp', webp_bytes)

        buf.seek(0)

        base_name = _slugify(safe_title) or 'pack'
        filename = f'{base_name}.wastickers' if total_files == 1 else f'{base_name}_{part_index}.wastickers'

        results.append((filename, buf))

    return results


def _slugify(text: str) -> str:
    keep = []
    for ch in text:
        if ch.isalnum():
            keep.append(ch)
        elif ch in (' ', '_', '-'):
            keep.append('_')
    slug = ''.join(keep).strip('_')
    # evite les noms de fichiers a rallonge
    return slug[:60] if slug else 'pack'


def files_count_for(total_stickers: int, batch_size: int = WaStickers.STICKERS_PER_FILE) -> int:
    return max(1, math.ceil(total_stickers / batch_size))
