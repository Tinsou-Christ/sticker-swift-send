import logging
import re
import datetime

# noinspection PyPackageRequirements
from telegram.error import BadRequest
from telegram.ext import (
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler
)
# noinspection PyPackageRequirements
from telegram import ChatAction, Update, Sticker

from bot import stickersbot
from bot.strings import Strings
from bot.database.base import session_scope
from bot.database.models.pack import Pack
from bot.markups import InlineKeyboard
from bot.stickers import StickerFile
from constants.stickers import StickerType as PackType, STICKER_TYPE_DESC
import bot.stickers.error as error
from ..conversation_statuses import Status
from ...utils import decorators
from ...utils import utils

logger = logging.getLogger(__name__)


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_create_pack_command(update: Update, context: CallbackContext):
    logger.info('/create')

    context.user_data['pack'] = dict(pack_type=PackType.STATIC)

    update.message.reply_html(
        Strings.PACK_CREATION_WAITING_TITLE,
        reply_markup=InlineKeyboard.pack_type_switch()
    )
    
    return Status.CREATE_WAITING_TITLE


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_pack_title_receive(update: Update, context: CallbackContext):
    logger.info('received possible pack title')

    if len(update.message.text) > 64:
        logger.info('pack title too long: %s', update.message.text)
        update.message.reply_text(Strings.PACK_TITLE_TOO_LONG)
        # do not change the user status and let him send another title
        return Status.CREATE_WAITING_TITLE

    if '\n' in update.message.text:
        logger.info('pack title contains newline character')
        update.message.reply_text(Strings.PACK_TITLE_CONTAINS_NEWLINES)
        # do not change the user status and let him send another title
        return Status.CREATE_WAITING_TITLE

    logger.info('pack title is valid')

    context.user_data['pack']['title'] = update.message.text

    # max len of a pack name = 64 - "_by_botusername", final string always added by the API
    max_name_len = 64 - (len(context.bot.username) + 4)

    text = Strings.PACK_CREATION_WAITING_NAME.format(update.message.text, max_name_len)
    update.message.reply_html(text)
    
    return Status.CREATE_WAITING_NAME


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_pack_name_receive(update: Update, context: CallbackContext):
    logger.info('received possible pack name (link)')
    logger.debug('user_data: %s', context.user_data)

    candidate_name = update.message.text
    max_name_len = 64 - (len(context.bot.username) + 4)
    if len(candidate_name) > max_name_len:
        logger.info('pack name too long (%d/%d)', len(candidate_name), max_name_len)
        update.message.reply_text(Strings.PACK_NAME_TOO_LONG.format(len(update.message.text), max_name_len))
        # do not change the user status and let him send another name
        return Status.CREATE_WAITING_NAME

    if not re.search(r'^[a-z](?!__)\w+$', candidate_name, re.IGNORECASE):
        logger.info('pack name not valid: %s', update.message.text)
        update.message.reply_html(Strings.PACK_NAME_INVALID)
        # do not change the user status and let him send another name
        return Status.CREATE_WAITING_NAME

    name_already_used = False
    with session_scope() as session:
        # https://stackoverflow.com/a/34112760
        if session.query(Pack).filter(Pack.user_id==update.effective_user.id, Pack.name==candidate_name).first() is not None:
            logger.info('pack name already saved: %s', candidate_name)
            name_already_used = True

    if name_already_used:
        update.message.reply_text(Strings.PACK_NAME_DUPLICATE)
        # do not change the user status and let him send another name
        return Status.CREATE_WAITING_NAME

    logger.info('valid pack name: %s', candidate_name)

    context.user_data['pack']['name'] = candidate_name

    if context.user_data['pack']['pack_type'] == PackType.ANIMATED:
        text = Strings.PACK_CREATION_WAITING_FIRST_ANIMATED_STICKER
    elif context.user_data['pack']['pack_type'] == PackType.VIDEO:
        text = Strings.PACK_CREATION_WAITING_FIRST_VIDEO_STICKER
    else:
        text = Strings.PACK_CREATION_WAITING_FIRST_STATIC_STICKER

    update.message.reply_text(text)

    return Status.CREATE_WAITING_FIRST_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_first_sticker_receive(update: Update, context: CallbackContext):
    logger.info('first stickers of the pack received')
    logger.debug('user_data: %s', context.user_data)

    user_emojis = context.user_data['pack'].get('emojis', None)  # we will pop this key later
    sticker_file = StickerFile(update.message, user_emojis)

    if sticker_file.type != context.user_data['pack']['pack_type']:
        expected_type = STICKER_TYPE_DESC.get(context.user_data['pack']['pack_type'])
        received_type = STICKER_TYPE_DESC.get(sticker_file.type)
        logger.info('invalid stickers, expected: %s, received: %s', expected_type, received_type)

        update.message.reply_text(Strings.ADD_STICKER_EXPECTING_DIFFERENT_TYPE.format(expected_type, received_type))
        return Status.CREATE_WAITING_FIRST_STICKER

    title, name = context.user_data['pack'].get('title', None), context.user_data['pack'].get('name', None)
    if not title or not name:
        logger.error('pack title or name missing (title: %s, name: %s)', title, name)
        update.message.reply_text(Strings.PACK_CREATION_FIRST_STICKER_PACK_DATA_MISSING)

        context.user_data.pop('pack', None)  # remove temp info

        return ConversationHandler.END

    full_name = '{}_by_{}'.format(name, context.bot.username)

    context.user_data['pack'].pop('emojis', None)  # make sure to pop emojis

    sticker_file.download()

    if sticker_file.is_static_sticker() and sticker_file.is_document():
        sticker_file.add_to_pack_prepare_sticker_document()  # will properly resize static stickers

    try:
        logger.debug('executing API request...')
        request_payload = {
            "user_id": update.effective_user.id,
            "title": title,
            "name": full_name,
            "emojis": sticker_file.get_emojis_str(),
            "sticker_type": Sticker.REGULAR,
            sticker_file.api_arg_name: sticker_file.get_input_file()
        }

        context.bot.create_new_sticker_set(**request_payload)
    except (error.PackInvalid, error.NameInvalid, error.NameAlreadyOccupied) as e:
        logger.error('Telegram error while creating stickers pack: %s', e.message)
        if isinstance(e, error.NameAlreadyOccupied):
            # there's already a pack with that link
            update.message.reply_html(Strings.PACK_CREATION_ERROR_DUPLICATE_NAME.format(utils.name2link(full_name)))
        elif isinstance(e, (error.PackInvalid, error.NameInvalid)):
            update.message.reply_text(Strings.PACK_CREATION_ERROR_INVALID_NAME)

        context.user_data['pack'].pop('name', None)  # remove pack name
        sticker_file.close()

        return Status.CREATE_WAITING_NAME  # do not continue, wait for another name
    except error.InvalidAnimatedSticker as e:
        logger.error('Telegram error while creating animated pack: %s', e.message)
        update.message.reply_html(Strings.ADD_STICKER_INVALID_ANIMATED, quote=True)

        return Status.CREATE_WAITING_FIRST_STICKER
    except error.FloodControlExceeded as e:
        logger.error('Telegram error while creating pack: %s', e.message)
        retry_in = re.search(r'retry in (\d+)(?:\.\d*)? seconds', e.message, re.I).group(1)  # Retry in 8 seconds

        retry_in_pretty = str(datetime.timedelta(seconds=int(retry_in)))
        text = Strings.ADD_STICKER_FLOOD_EXCEPTION.format(retry_in_pretty)

        update.message.reply_html(text, quote=True)

        return ConversationHandler.END  # do not continue, end the conversation
    except error.UnknwonError as e:
        logger.error('Unknown error while creating the pack: %s', e.message)
        update.message.reply_html(Strings.PACK_CREATION_ERROR_GENERIC.format(e.message))

        context.user_data.pop('pack', None)  # remove temp data
        sticker_file.close()

        return ConversationHandler.END  # do not continue, end the conversation
    else:
        # success

        pack_row = Pack(user_id=update.effective_user.id, name=full_name, title=title, pack_type=sticker_file.type)
        with session_scope() as session:
            session.add(pack_row)

        # db.save_pack(update.effective_user.id, full_name, title)
        pack_link = utils.name2link(full_name)
        update.message.reply_html(Strings.PACK_CREATION_PACK_CREATED.format(pack_link))

        sticker_file.close()  # remove stickers files

        context.user_data['pack']['name'] = full_name
        # do not remove temporary data (user_data['pack']) because we are still adding stickers

        # wait for other stickers
        return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_first_sticker_text_receive(update: Update, context: CallbackContext):
    logger.info('user sent a text message while we were waiting for the first stickers of a pack')
    logger.debug('user_data: %s', context.user_data)

    emojis = utils.get_emojis(update.message.text, as_list=True)
    if not emojis:
        update.message.reply_text(Strings.ADD_STICKER_NO_EMOJI_IN_TEXT)
        return Status.CREATE_WAITING_FIRST_STICKER
    elif len(emojis) > 10:
        update.message.reply_text(Strings.ADD_STICKER_TOO_MANY_EMOJIS)
        return Status.CREATE_WAITING_FIRST_STICKER

    context.user_data['pack']['emojis'] = emojis

    update.message.reply_text(Strings.ADD_STICKER_EMOJIS_SAVED.format(
        len(emojis),
        ''.join(emojis)
    ))

    return Status.CREATE_WAITING_FIRST_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_title_invalid_message(update: Update, _):
    logger.info('(create) waiting title: wrong type of message received')

    update.message.reply_html(Strings.PACK_TITLE_INVALID_MESSAGE)

    return Status.CREATE_WAITING_TITLE


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_name_invalid_message(update: Update, _):
    logger.info('(create) waiting name: wrong type of message received')

    update.message.reply_html(Strings.PACK_NAME_INVALID_MESSAGE)

    return Status.CREATE_WAITING_NAME


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_first_sticker_invalid_message(update: Update, _):
    logger.info('waiting first stickers: wrong type of message received')

    update.message.reply_html(Strings.PACK_CREATION_WAITING_FIRST_STICKER_INVALID_MESSAGE)

    return Status.CREATE_WAITING_FIRST_STICKER


@decorators.failwithmessage
def on_switch_pack_type(update: Update, context: CallbackContext):
    logger.info('swicth pack type inline keyboard')

    if not context.user_data.get('pack', None):
        update.callback_query.answer(Strings.PACK_TYPE_BUTTONS_EXPIRED)
        update.callback_query.message.edit_reply_markup(reply_markup=InlineKeyboard.REMOVE)
        return

    match: int = int(context.matches[0].group(1))
    reply_markup = InlineKeyboard.pack_type_switch(match)

    if match == PackType.ANIMATED:
        context.user_data['pack']['pack_type'] = PackType.ANIMATED
    elif match == PackType.VIDEO:
        context.user_data['pack']['pack_type'] = PackType.VIDEO
    else:
        context.user_data['pack']['pack_type'] = PackType.STATIC

    try:
        update.callback_query.message.edit_reply_markup(reply_markup=reply_markup)
    except BadRequest:
        pass

    pack_type_description = STICKER_TYPE_DESC[match]
    update.callback_query.answer(Strings.PACK_TYPE_CHANGED.format(pack_type_description))


stickersbot.add_handler(CallbackQueryHandler(on_switch_pack_type, pattern='packtype:(.+)'))

