import logging
import re

# noinspection PyPackageRequirements
from telegram import ChatAction, Update, Sticker, StickerSet
# noinspection PyPackageRequirements
from telegram.error import BadRequest, TelegramError
# noinspection PyPackageRequirements
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    Filters
)

from bot import stickersbot
from bot.database.base import session_scope
from bot.database.models.pack import Pack
from bot.strings import Strings
from ..conversation_statuses import Status
from ..fallback_commands import cancel_command, on_timeout
from ...customfilters import CustomFilters
from ...utils import decorators
from ...utils import utils

logger = logging.getLogger(__name__)

PACK_SUFFIX = f"_by_{stickersbot.bot.username}"

DUMMY_EMOJI = "🧱"  # possibly an emoji that nobody would use


def check_pack_name(user_id: int, pack_name: str, context: CallbackContext) -> [None, str]:
    """no longer used"""

    pack_link = utils.name2link(pack_name, context.bot.username)

    if not re.search(r"^[a-z0-9][a-z0-9_]+[a-z0-9]$", pack_name, re.I):  # needs to be improved
        return Strings.READD_INVALID_PACK_NAME_PATTERN

    if not pack_name.endswith(PACK_SUFFIX):
        return Strings.READD_WRONG_PACK_NAME.format(pack_link, PACK_SUFFIX)

    with session_scope() as session:
        pack_exists = session.query(Pack).filter_by(name=pack_name, user_id=user_id).first() is not None

    if pack_exists:
        return Strings.READD_PACK_EXISTS.format(pack_link)


def process_pack(sticker: Sticker, update: Update, context: CallbackContext):
    pack_link = utils.name2link(sticker.set_name, context.bot.username)

    dummy_file_name = "dummy_sticker.png" if not sticker.is_animated else "dummy_sticker.tgs"
    add_request_file_kwarg = "png_sticker" if not sticker.is_animated else "tgs_sticker"

    add_sticker_to_set_kwargs = dict(
        user_id=update.effective_user.id,
        name=sticker.set_name,
        emojis=DUMMY_EMOJI
    )

    try:
        with open(f"assets/{dummy_file_name}", "rb") as f:
            add_sticker_to_set_kwargs[add_request_file_kwarg] = f
            context.bot.add_sticker_to_set(**add_sticker_to_set_kwargs)

        logger.debug("successfully added dummy stickers to pack <%s>", sticker.set_name)
    except (TelegramError, BadRequest) as e:
        error_message = e.message.lower()
        if "stickerset_invalid" in error_message:
            update.message.reply_html(Strings.READD_PACK_INVALID.format(pack_link))
            return Status.WAITING_STICKER
        else:
            logger.error("/readd: api error while adding dummy stickers to pack <%s>: %s", sticker.set_name, e.message)
            update.message.reply_html(Strings.READD_UNKNOWN_API_EXCEPTION.format(pack_link, e.message))
            return Status.WAITING_STICKER

    # we make a quick check whether the stickers we just added is returned by get_sticker_set()
    # if not, we will leave the stickers we just added there
    # see long comment below
    sticker_set: StickerSet = context.bot.get_sticker_set(sticker.set_name)
    if sticker_set.stickers[-1].emoji == DUMMY_EMOJI:
        sticker_to_remove = sticker_set.stickers[-1]
    else:
        logger.warning("dummy emoji and the emoji of the last stickers in the set do not match")
        sticker_to_remove = None

    pack_row = Pack(
        user_id=update.effective_user.id,
        name=sticker_set.name,
        title=sticker_set.title,
        is_animated=sticker_set.is_animated
    )
    with session_scope() as session:
        session.add(pack_row)

    stickerset_title_link = utils.stickerset_title_link(sticker_set)
    update.message.reply_html(
        Strings.READD_SAVED.format(stickerset_title_link)
    )

    # We do this here to let the API figure out we just added the stickers with that file_id to the pack
    # it will raise an exception anyway though (Sticker_invalid)
    # we might just ignore it. The user now can manage the pack, and can remove the dummy stickers manually
    # Also, it might be the case (IT *IS* THE CASE) that the dummy stickers added to the pack gets its own file_id, so
    # the file_id returned by upload_sticker_file should be used to remove the stickers.
    # We then use the file_id of the last stickers in the pack, but I guess we can't be 100% sure
    # the get_sticker_set request returned the pack with also the dummy stickers we added one second before
    if not sticker_to_remove:
        # the dummy emoji and the emoji of the last stickers in the pack did not match
        update.message.reply_html(Strings.READD_DUMMY_STICKER_NOT_REMOVED)
    else:
        try:
            context.bot.delete_sticker_from_set(sticker=sticker_to_remove.file_id)
            logger.debug("successfully removed dummy stickers from pack <%s>", sticker.set_name)
        except (TelegramError, BadRequest) as e:
            error_message = e.message.lower()
            if "sticker_invalid" in error_message:
                update.message.reply_html(Strings.READD_DUMMY_STICKER_NOT_REMOVED)
            else:
                logger.error("/readd: api error while removing dummy stickers from pack <%s>: %s", sticker.set_name, e.message)
                update.message.reply_html(Strings.READD_DUMMY_STICKER_NOT_REMOVED_UNKNOWN.format(error_message))

    return ConversationHandler.END


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_readd_command(update: Update, context: CallbackContext):
    logger.info('/readd')

    update.message.reply_text(Strings.READD_WAITING_STICKER)

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_sticker_received(update: Update, context: CallbackContext):
    logger.info('/readd: stickers received')

    sticker: Sticker = update.message.sticker
    if not sticker.set_name:
        update.message.reply_html(Strings.READD_STICKER_NO_PACK)

        return Status.WAITING_STICKER

    return process_pack(sticker, update, context)


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_pack_animated_sticker(update: Update, context: CallbackContext):
    logger.info('/readd: animated stickers received')

    update.message.reply_html(Strings.READD_STICKER_ANIMATED)

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_pack_unexpected_message(update: Update, context: CallbackContext):
    logger.info('/readd: unexpected message')

    update.message.reply_html(Strings.READD_UNEXPECTED_MESSAGE)

    return Status.WAITING_STICKER


stickersbot.add_handler(ConversationHandler(
    name='readd_command',
    persistent=False,
    entry_points=[CommandHandler(['readd', 'rea', 'ra'], on_readd_command)],
    states={
        Status.WAITING_STICKER: [
            MessageHandler(Filters.sticker, on_sticker_received),
            MessageHandler(Filters.all & ~CustomFilters.done_or_cancel, on_waiting_pack_unexpected_message),
        ],
        ConversationHandler.TIMEOUT: [MessageHandler(Filters.all, on_timeout)]
    },
    fallbacks=[CommandHandler(['cancel', 'c', 'done', 'd'], cancel_command)],
    # conversation_timeout=15 * 60
))
