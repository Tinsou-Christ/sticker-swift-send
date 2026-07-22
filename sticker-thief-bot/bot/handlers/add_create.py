import logging

# noinspection PyPackageRequirements
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    Filters
)

from bot import stickersbot
from constants.commands import Commands
from .conversation_statuses import Status
from .fallback_commands import cancel_command, on_timeout
from .packs import create
from .stickers import add
from ..customfilters import CustomFilters

logger = logging.getLogger(__name__)


stickersbot.add_handler(ConversationHandler(
    name='create_or_add',
    persistent=True,
    entry_points=[
        # CREATE
        CommandHandler(['create', 'new'], create.on_create_pack_command),
        # ADD
        CommandHandler(['add', 'a'], add.on_add_command)
    ],
    states={
        # CREATE
        Status.CREATE_WAITING_TITLE: [
            MessageHandler(Filters.text & ~Filters.command(Commands.STANDARD_CANCEL_COMMANDS), create.on_pack_title_receive),
            MessageHandler(~Filters.text, create.on_waiting_title_invalid_message)
        ],
        Status.CREATE_WAITING_NAME: [
            MessageHandler(Filters.text & ~Filters.command(Commands.STANDARD_CANCEL_COMMANDS), create.on_pack_name_receive),
            MessageHandler(~Filters.text, create.on_waiting_name_invalid_message)
        ],
        Status.CREATE_WAITING_FIRST_STICKER: [
            MessageHandler(Filters.text & ~Filters.command, create.on_first_sticker_text_receive),  # in case the user sends the emojis
            # this handler is shared by all types of stickers
            MessageHandler(Filters.sticker | CustomFilters.supported_file | CustomFilters.raw_media, create.on_first_sticker_receive),
            MessageHandler(~CustomFilters.done_or_cancel, create.on_waiting_first_sticker_invalid_message)
        ],

        # ADD
        Status.ADD_WAITING_TITLE: [
            MessageHandler(~Filters.text, add.on_waiting_title_invalid_message),
            MessageHandler(Filters.text & ~Filters.command(Commands.STANDARD_CANCEL_COMMANDS), add.on_pack_title)
        ],
        Status.ADD_WAITING_NAME: [
            MessageHandler(~Filters.text, add.on_waiting_name_invalid_message),
            MessageHandler(Filters.text & ~Filters.command(Commands.STANDARD_CANCEL_COMMANDS), add.on_pack_name)
        ],

        # ADD (shared by /add et /create)
        Status.WAITING_STICKER: [
            MessageHandler(Filters.text & ~Filters.command, add.on_text_receive),  # in case the user sends the emojis
            MessageHandler(Filters.sticker | CustomFilters.supported_file | CustomFilters.raw_media, add.on_sticker_receive),
            # for everything that is not catched by the handlers above
            MessageHandler(Filters.all & ~Filters.command(Commands.STANDARD_CANCEL_COMMANDS), add.on_waiting_sticker_invalid_message)
        ],

        # TIMEOUT
        ConversationHandler.TIMEOUT: [MessageHandler(Filters.all, on_timeout)]
    },
    fallbacks=[CommandHandler(Commands.STANDARD_CANCEL_COMMANDS, cancel_command)],
    conversation_timeout=15 * 60
))
