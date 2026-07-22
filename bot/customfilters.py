# noinspection PyPackageRequirements
import re

from telegram.ext import MessageFilter

from constants.stickers import MimeType
from constants.commands import CommandRegex


class AnimatedSticker(MessageFilter):
    def filter(self, message):
        if message.sticker and message.sticker.is_animated:
            return True


class VideoSticker(MessageFilter):
    def filter(self, message):
        if message.sticker and message.sticker.is_video:
            return True


class StaticSticker(MessageFilter):
    def filter(self, message):
        if message.sticker and not message.sticker.is_animated and not message.sticker.is_video:
            return True


class StaticStickerOrPngFile(MessageFilter):
    def filter(self, message):
        if (message.sticker and not message.sticker.is_animated) or (message.document and message.document.mime_type.startswith('image/png')):
            return True


class NonVideoSticker(MessageFilter):
    def filter(self, message):
        if message.sticker and not message.sticker.is_video:
            return True


class PngFile(MessageFilter):
    def filter(self, message):
        if message.document and message.document.mime_type.startswith(MimeType.PNG):
            return True


class WebmFile(MessageFilter):
    def filter(self, message):
        if message.document and message.document.mime_type.startswith(MimeType.WEBM):
            return True


class SupportedFile(MessageFilter):
    def filter(self, message):
        if message.document and message.document.mime_type.startswith((MimeType.WEBP, MimeType.PNG, MimeType.WEBM)):
            return True


class RawMedia(MessageFilter):
    def filter(self, message):
        if message.photo or message.video or message.animation:
            return True


class Cancel(MessageFilter):
    def filter(self, message):
        if message.text and re.search(CommandRegex.CANCEL, message.text, re.I):
            return True


class Done(MessageFilter):
    def filter(self, message):
        if message.text and re.search(CommandRegex.DONE, message.text, re.I):
            return True


class DoneOrCancel(MessageFilter):
    def filter(self, message):
        if message.text and re.search(CommandRegex.DONE_OR_CANCEL, message.text, re.I):
            return True


class StickerOrCancel(MessageFilter):
    def filter(self, message):
        if message.sticker or (message.text and re.search(CommandRegex.DONE_OR_CANCEL, message.text, re.I)):
            return True


class CustomFilters:
    animated_sticker = AnimatedSticker()
    video_sticker = VideoSticker()
    static_sticker = StaticSticker()
    non_video_sticker = NonVideoSticker()
    static_sticker_or_png_file = StaticStickerOrPngFile()
    png_file = PngFile()
    webm_file = WebmFile()
    supported_file = SupportedFile()
    raw_media = RawMedia()
    cancel = Cancel()
    done = Done()
    done_or_cancel = DoneOrCancel()
    sticker_or_cancel = StickerOrCancel()
