# noinspection PyPackageRequirements
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from constants.stickers import StickerType


class InlineKeyboard:
    HIDE = None
    REMOVE = None

    @staticmethod
    def pack_type_switch(sticker_type: int = StickerType.STATIC):
        static_button = InlineKeyboardButton(
            '{} static'.format('✅' if sticker_type == StickerType.STATIC else '☑️'),
            callback_data=f'packtype:{StickerType.STATIC}'
        )
        animated_button = InlineKeyboardButton(
            '{} animated'.format('✅' if sticker_type == StickerType.ANIMATED else '☑️'),
            callback_data=f'packtype:{StickerType.ANIMATED}'
        )
        video_button = InlineKeyboardButton(
            '{} video'.format('✅' if sticker_type == StickerType.VIDEO else '☑️'),
            callback_data=f'packtype:{StickerType.VIDEO}'
        )

        return InlineKeyboardMarkup([[static_button, animated_button, video_button]])
