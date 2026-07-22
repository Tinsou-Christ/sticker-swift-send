class StickerType:
    STATIC = 10
    ANIMATED = 20
    VIDEO = 30


class MimeType:
    PNG = "image/png"
    WEBP = "image/webp"
    WEBM = "video/webm"


class MaxPackSize:
    STATIC = 120
    ANIMATED = 50
    VIDEO = 120


STICKER_TYPE_DESC = {
    StickerType.STATIC: "static",
    StickerType.ANIMATED: "animated",
    StickerType.VIDEO: "video"
}

MAX_PACK_SIZE = {
    StickerType.STATIC: MaxPackSize.STATIC,
    StickerType.ANIMATED: MaxPackSize.ANIMATED,
    StickerType.VIDEO: MaxPackSize.VIDEO
}


class WaStickers:
    STICKERS_PER_FILE = 30  # WhatsApp/Sticker Maker: max 30 stickers par fichier .wastickers
    STATIC_MAX_BYTES = 100 * 1024  # limite "soft" WhatsApp pour un sticker statique (100 KB)
    ANIMATED_MAX_BYTES = 480 * 1024  # limite WhatsApp pour un sticker anime (~500 KB, marge de securite)
    TRAY_ICON_MAX_BYTES = 50 * 1024  # limite de l'icone du tray (96x96 png)
    TRAY_ICON_SIZE = 96
    STICKER_SIZE = 512
    TITLE_MAX_LEN = 128
    AUTHOR_MAX_LEN = 128
    
