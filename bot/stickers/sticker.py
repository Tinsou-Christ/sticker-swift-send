import logging
import os
import tempfile
# noinspection PyPackageRequirements
from typing import Union, Optional

from telegram import Sticker, Document, InputFile, Bot, Message, File, MessageEntity

from constants.stickers import StickerType, MimeType
from ..utils import image
from ..utils import converter
from ..utils.pyrogram import get_sticker_emojis

# noinspection PyPackageRequirements

logger = logging.getLogger('StickerFile')


class MessageScaffold:
    def __init__(self, sticker: Sticker):
        self.sticker = sticker
        self.document = None


class StickerFile:
    DEFAULT_EMOJI = '🎭'

    def __init__(self, message: Union[Message, MessageScaffold], emojis: Optional[list] = None, tempfile_to_use: Optional[tempfile.TemporaryFile] = None):
        self.type = None
        self.raw_media = False  # True si photo/video/gif brut necessitant une conversion ffmpeg
        self.sticker: Union[Sticker, Document] = message.sticker or message.document
        self.sticker_tempfile = tempfile_to_use or tempfile.SpooledTemporaryFile()  # bytes object to pass to the api

        if self.sticker is None and getattr(message, 'photo', None):
            self.raw_media = True
            self.sticker = message.photo[-1]  # plus haute resolution disponible
            self.type = StickerType.STATIC
        elif self.sticker is None and getattr(message, 'video', None):
            self.raw_media = True
            self.sticker = message.video
            self.type = StickerType.VIDEO
        elif self.sticker is None and getattr(message, 'animation', None):
            self.raw_media = True
            self.sticker = message.animation
            self.type = StickerType.VIDEO
        elif self.is_sticker() and not self.sticker.is_animated and not self.sticker.is_video:
            self.type = StickerType.STATIC
        elif self.is_sticker() and self.sticker.is_animated:
            self.type = StickerType.ANIMATED
        elif self.is_sticker() and self.sticker.is_video:
            self.type = StickerType.VIDEO
        elif self.is_document(MimeType.PNG) or self.is_document(MimeType.WEBP):
            self.type = StickerType.STATIC
        elif self.is_document(MimeType.WEBM):
            self.type = StickerType.VIDEO
        else:
            raise ValueError("could not detect stickers type")

        if emojis:
            # user-specified emojis has been passed
            # eg. the user sent some emojis before sending the stickers
            self.emojis = emojis
        elif self.raw_media:
            self.emojis = [self.DEFAULT_EMOJI]
        elif self.is_sticker() and not self.sticker.emoji:
            logger.info("the stickers doesn't have a pack, using default emoji")
            self.emojis = [self.DEFAULT_EMOJI]
        else:
            self.emojis = get_sticker_emojis(message) or [self.DEFAULT_EMOJI]

        logger.debug('emojis: %s', self.emojis)

    @classmethod
    def from_entity(cls, custom_emoji: MessageEntity.CUSTOM_EMOJI, bot: Bot):
        sticker: Sticker = bot.get_custom_emoji_stickers([custom_emoji.custom_emoji_id])[0]
        fake_message = MessageScaffold(sticker)

        return cls(fake_message)

    @property
    def file_unique_id(self):
        return self.sticker.file_unique_id

    @property
    def api_arg_name(self):
        if self.is_animated_sticker():
            return "tgs_sticker"
        elif self.is_video_sticker():
            return "webm_sticker"
        else:
            return "png_sticker"

    def is_document(self, mime_type: Optional[str] = None):
        is_document = isinstance(self.sticker, Document)

        if not is_document:
            return False
        elif not mime_type:
            return True
        else:
            return self.sticker.mime_type.startswith(mime_type)

    def is_sticker(self):
        return isinstance(self.sticker, Sticker)

    def is_static_sticker(self):
        return self.type == StickerType.STATIC

    def is_animated_sticker(self):
        return self.type == StickerType.ANIMATED

    def is_video_sticker(self):
        return self.type == StickerType.VIDEO

    def type_str(self):
        if self.type == StickerType.STATIC:
            return "static"
        elif self.type == StickerType.ANIMATED:
            return "animated"
        elif self.type == StickerType.VIDEO:
            return "video"
        else:
            return "unknown"

    def get_extension(self, png=False, dot=False):
        prefix = "." if dot else ""
        if self.type == StickerType.STATIC and self.is_document(MimeType.PNG):
            return f"{prefix}png"
        elif self.type == StickerType.STATIC and self.is_document(MimeType.WEBP):
            return f"{prefix}webp"
        elif self.type == StickerType.STATIC:
            return f"{prefix}webp" if not png else f"{prefix}png"
        elif self.type == StickerType.ANIMATED:
            return f"{prefix}tgs"
        elif self.type == StickerType.VIDEO:
            return f"{prefix}webm"

    def patch_tempfile_name(self):
        name = f"{self.file_unique_id}.{self.get_extension()}"
        self.sticker_tempfile.name = name

    def file_name(self, *args, **kwargs):
        return f"{self.file_unique_id}.{self.get_extension(*args, **kwargs)}"

    def get_emojis_str(self) -> str:
        if not isinstance(self.emojis, (list, tuple)):
            raise ValueError('StickerFile.emojis is not of type list/tuple (type: {})'.format(type(self.emojis)))

        return "".join(self.emojis)

    def sticker_tempfile_seek(self):
        self.sticker_tempfile.seek(0)
        return self.sticker_tempfile

    def get_input_file(self):
        """returns a telegram InputFile"""
        if self.is_animated_sticker():
            extension = "tgs"
        elif self.is_video_sticker():
            extension = "webm"
        elif self.is_document(MimeType.PNG):
            extension = "png"
        else:
            extension = "webp"

        self.sticker_tempfile.seek(0)  # just to make sure

        return InputFile(self.sticker_tempfile, filename=f"{self.file_unique_id}.{extension}")

    def download(self):
        logger.debug('downloading stickers')
        new_file: File = self.sticker.get_file()

        if self.raw_media:
            logger.debug('downloading raw media (photo/video/gif) to convert it via ffmpeg')

            with tempfile.NamedTemporaryFile(delete=False) as tmp_in:
                input_path = tmp_in.name

            try:
                new_file.download(custom_path=input_path)

                if self.type == StickerType.STATIC:
                    converter.convert_image_to_webp(input_path, self.sticker_tempfile)
                else:
                    converter.convert_video_to_webm(input_path, self.sticker_tempfile)
            finally:
                if os.path.exists(input_path):
                    os.remove(input_path)

            self.sticker_tempfile.seek(0)
        else:
            logger.debug('downloading to bytes object')
            new_file.download(out=self.sticker_tempfile)
            self.sticker_tempfile.seek(0)

    def close(self):
        # noinspection PyBroadException
        try:
            self.sticker_tempfile.close()
        except Exception as e:
            logger.error('error while trying to close stickers tempfile: %s', str(e))

    def add_to_pack_prepare_sticker_document(self):
        # shortcut method to make sure a document is ready to be added to a pack

        if not self.is_static_sticker() and not self.is_document():
            raise ValueError("sticker is not static or is not a `telegram.Document` instance")

        options = image.Options(image_format=self.get_extension(), max_size=512)
        im = image.File(self.sticker_tempfile, options)

        # check whether we need to resize png/webp documents or not
        if im.sticker_needs_resize():
            logger.info("resizing %s file...", options.image_format)
            im.process()
            # override the sticker tempfile, we need a better way to do that
            self.sticker_tempfile = im.clone_result_tempfile(then_close=True)
        else:
            im.close()

    def __repr__(self):
        return 'StickerFile object of original origin {} (type: {})'.format(
            'Sticker' if self.is_sticker() else 'Document',
            self.type_str()
        )
