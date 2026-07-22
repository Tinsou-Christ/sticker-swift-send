import logging

# noinspection PyPackageRequirements
from telegram import ChatAction, Update, Message, ParseMode, MessageEntity, InputFile, Chat
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
# noinspection PyPackageRequirements

logger = logging.getLogger(__name__)


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_tofile_command(update: Update, context: CallbackContext):
    logger.info('/tofile')

    options = {
        "-png": ("png", "<code>send static stickers as png instead of webp</code>")
    }

    enabled_options_description = utils.check_flags(options, context, pop_existing_flags=True)

    update.message.reply_text(Strings.TO_FILE_WAITING_STICKER)
    if enabled_options_description:
        update.message.reply_html(f"{Strings.ENABLED_FLAGS}{' + '.join(enabled_options_description)}")

    return Status.WAITING_STICKER


@decorators.restricted
@decorators.action(ChatAction.UPLOAD_DOCUMENT)
@decorators.failwithmessage
def on_sticker_received(update: Update, context: CallbackContext):
    logger.info('user sent a sticker to convert')

    sticker_file = StickerFile(update.message)
    sticker_file.download()

    request_kwargs = dict(
        caption=sticker_file.get_emojis_str(),
        document=sticker_file.sticker_tempfile_seek(),
        disable_content_type_detection=True,
        quote=True
    )

    static_sticker_as_png = "png" in context.user_data

    if update.message.sticker.is_animated:
        request_kwargs['filename'] = f"{update.message.sticker.file_unique_id}.tgs"
    elif update.message.sticker.is_video:
        request_kwargs['filename'] = f"{update.message.sticker.file_unique_id}.webm"
    elif static_sticker_as_png:
        logger.debug("converting webp to png")
        im = image.File(sticker_file.sticker_tempfile, image.Options(image_format="png"))
        im.process()
        png_file = im.clone_result_tempfile(then_close=True)

        request_kwargs['document'] = png_file
        request_kwargs['filename'] = f"{update.message.sticker.file_unique_id}.png"
    else:
        request_kwargs['filename'] = f"{update.message.sticker.file_unique_id}.webp"

    sent_message: Message = update.message.reply_document(**request_kwargs)
    sticker_file.close()

    if sent_message.document:
        # only do this when we send the message as document
        # it will be useful to test problems with animated stickers. For example in mid 2020, the API started
        # to consider any animated stickers as invalid ("wrong file type" exception), and they were sent
        # back as file with a specific mimetype ("something something bad animated stickers"). In this way:
        # - sent back as animated stickers: everything ok
        # - sent back as file: there's something wrong with the code/api, better to edit the document with its mimetype
        sent_message.edit_caption(
            caption='{}\n<code>{}</code>'.format(
                sent_message.caption,
                Strings.TO_FILE_MIME_TYPE.format(sent_message.document.mime_type)
            ),
            parse_mode=ParseMode.HTML
        )
    elif sent_message.sticker:
        update.message.reply_text(Strings.ANIMATED_STICKERS_NO_FILE)

    return Status.WAITING_STICKER


@decorators.restricted
@decorators.action(ChatAction.UPLOAD_DOCUMENT)
@decorators.failwithmessage
def on_custom_emoji_receive(update: Update, context: CallbackContext):
    logger.info('user sent a custom emoji to convert')
    message = update.effective_message  # might be needed in channels

    if len(message.entities) > 1:
        message.reply_html(Strings.EMOJI_TO_FILE_TOO_MANY_ENTITIES, quote=True)
        return Status.WAITING_STICKER

    sticker_file: StickerFile = StickerFile.from_entity(message.entities[0], context.bot)
    sticker_file.download()

    logger.debug('downloading to bytes object')
    sticker_file.download()

    png_tempfile = None
    if update.effective_chat.type != Chat.CHANNEL and "png" in context.user_data:
        im = image.File(sticker_file.sticker_tempfile, image.Options(image_format="png"))
        im.process()
        png_tempfile = im.clone_result_tempfile(then_close=True)

    file_to_send = png_tempfile or sticker_file.sticker_tempfile
    extension = sticker_file.get_extension(png=bool(png_tempfile))
    input_file = InputFile(file_to_send, filename=f"{sticker_file.file_unique_id}.{extension}")

    message.reply_document(input_file, disable_content_type_detection=True, caption=sticker_file.get_emojis_str(), quote=True)
    sticker_file.close()

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_sticker_unexpected_message(update: Update, context: CallbackContext):
    logger.info('/tofile: unexpected message')

    update.message.reply_html(Strings.TO_FILE_UNEXPECTED_MESSAGE)

    return Status.WAITING_STICKER


stickersbot.add_handler(ConversationHandler(
    name='tofile_command',
    persistent=False,
    entry_points=[CommandHandler(['tofile', 'tf'], on_tofile_command)],
    states={
        Status.WAITING_STICKER: [
            CommandHandler(['tofile', 'tf'], on_tofile_command),
            MessageHandler(Filters.sticker, on_sticker_received),
            MessageHandler(Filters.entity(MessageEntity.CUSTOM_EMOJI), on_custom_emoji_receive),
            MessageHandler(Filters.all & ~CustomFilters.done_or_cancel, on_waiting_sticker_unexpected_message),
        ],
        ConversationHandler.TIMEOUT: [MessageHandler(Filters.all, on_timeout)]
    },
    fallbacks=[CommandHandler(['cancel', 'c', 'done', 'd'], cancel_command)],
    conversation_timeout=15 * 60
))

stickersbot.add_handler(MessageHandler(Filters.chat_type.channel & Filters.entity(MessageEntity.CUSTOM_EMOJI), on_custom_emoji_receive))
