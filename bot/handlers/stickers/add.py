import logging
import re
# noinspection PyPackageRequirements
from typing import List

# noinspection PyPackageRequirements
from telegram import ChatAction, Update
from telegram.ext import (
    ConversationHandler,
    CallbackContext
)

import bot.stickers.error as error
from bot.database.base import session_scope
from bot.database.models.pack import Pack
from bot.markups import Keyboard
from bot.stickers import StickerFile, send_request
from bot.strings import Strings
from constants.stickers import StickerType, STICKER_TYPE_DESC, MAX_PACK_SIZE
from ..conversation_statuses import Status
from ...utils import decorators
from ...utils import utils

logger = logging.getLogger(__name__)


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def on_add_command(update: Update, _):
    logger.info('/add')

    user_id = update.effective_user.id

    with session_scope() as session:
        pack_titles = [t.title for t in session.query(Pack.title).filter_by(user_id=user_id).order_by(Pack.title).all()]

    if not pack_titles:
        update.message.reply_text(Strings.ADD_STICKER_NO_PACKS)

        return ConversationHandler.END
    else:
        markup = Keyboard.from_list(pack_titles)
        update.message.reply_text(Strings.ADD_STICKER_SELECT_PACK, reply_markup=markup)

        return Status.ADD_WAITING_TITLE


def get_add_stickers_string(pack_type):
    if pack_type == StickerType.STATIC:
        return Strings.ADD_STICKER_PACK_SELECTED_STATIC
    elif pack_type == StickerType.ANIMATED:
        return Strings.ADD_STICKER_PACK_SELECTED_ANIMATED
    else:
        return Strings.ADD_STICKER_PACK_SELECTED_VIDEO


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_pack_title(update: Update, context: CallbackContext):
    logger.info('user selected the pack title from the keyboard')

    selected_title = update.message.text
    user_id = update.effective_user.id

    with session_scope() as session:
        packs_by_title: List[Pack] = session.query(Pack).filter_by(title=selected_title, user_id=user_id).order_by(Pack.name).all()

        # for some reason, accessing a Pack attribute outside of a session
        # raises an error: https://docs.sqlalchemy.org/en/13/errors.html#object-relational-mapping
        # so we preload the list here in case we're going to need it later, to avoid a more complex handling
        # of the session
        by_bot_part = '_by_' + context.bot.username
        pack_names = [pack.name.replace(by_bot_part, '', 1) for pack in packs_by_title]  # strip the '_by_bot' part
        pack_type = packs_by_title[0].type_patched()  # we need this in case there's only one pack and we need to know whether it is animated or not

    if not packs_by_title:
        logger.error('cannot find any pack with this title: %s', selected_title)
        update.message.reply_text(Strings.ADD_STICKER_SELECTED_TITLE_DOESNT_EXIST.format(selected_title[:150]))
        # do not change the user status
        return Status.ADD_WAITING_TITLE

    if len(packs_by_title) > 1:
        logger.info('user has multiple packs with this title: %s', selected_title)

        markup = Keyboard.from_list(pack_names, add_back_button=True)

        # list with the links to the involved packs
        pack_links = ['<a href="{}">{}</a>'.format(utils.name2link(pack_name, bot_username=context.bot.username), pack_name) for pack_name in pack_names]
        text = Strings.ADD_STICKER_SELECTED_TITLE_MULTIPLE.format(selected_title, '\n• '.join(pack_links))
        update.message.reply_html(text, reply_markup=markup)

        return Status.ADD_WAITING_NAME  # we now have to wait for the user to tap on a pack name

    logger.info('there is only one pack with the selected title (pack type: %s), proceeding...', pack_type)
    pack_name = '{}_by_{}'.format(pack_names[0], context.bot.username)

    context.user_data['pack'] = dict(name=pack_name, pack_type=pack_type)
    pack_link = utils.name2link(pack_name)
    base_string = get_add_stickers_string(pack_type)
    update.message.reply_html(base_string.format(pack_link), reply_markup=Keyboard.HIDE)

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_pack_name(update: Update, context: CallbackContext):
    logger.info('user selected the pack name from the keyboard')
    logger.debug('user_data: %s', context.user_data)

    if re.search(r'^GO BACK$', update.message.text, re.I):
        with session_scope() as session:
            pack_titles = [t.title for t in session.query(Pack.title).filter_by(user_id=update.effective_user.id).all()]

        markup = Keyboard.from_list(pack_titles)
        update.message.reply_text(Strings.ADD_STICKER_SELECT_PACK, reply_markup=markup)

        return Status.ADD_WAITING_TITLE

    # the buttons list has the name without "_by_botusername"
    selected_name = '{}_by_{}'.format(update.message.text, context.bot.username)

    with session_scope() as session:
        pack = session.query(Pack).filter_by(name=selected_name, user_id=update.effective_user.id).first()
        pack_name = pack.name
        pack_type = pack.type_patched()

    if not pack_name:
        logger.error('user %d does not have any pack with name %s', update.effective_user.id, selected_name)
        update.message.reply_text(Strings.ADD_STICKER_SELECTED_NAME_DOESNT_EXIST)
        # do not reset the user status
        return Status.ADD_WAITING_NAME

    context.user_data['pack'] = dict(name=pack_name, pack_type=pack_type)
    pack_link = utils.name2link(pack_name)
    base_string = get_add_stickers_string(pack_type)
    update.message.reply_html(base_string.format(pack_link), reply_markup=Keyboard.HIDE)

    return Status.WAITING_STICKER


def add_sticker_to_set(update: Update, context: CallbackContext):
    pack_name = context.user_data['pack'].get('name', None)
    if not pack_name:
        logger.error('pack name missing (%s)', pack_name)
        update.message.reply_text(Strings.ADD_STICKER_PACK_DATA_MISSING)

        context.user_data.pop('pack', None)  # remove temp info

        return ConversationHandler.END

    user_emojis = context.user_data['pack'].pop('emojis', None)  # we also remove them
    sticker_file = StickerFile(update.message, emojis=user_emojis)
    sticker_file.download()

    if sticker_file.is_static_sticker() and sticker_file.is_document():
        sticker_file.add_to_pack_prepare_sticker_document()  # will properly resize static stickers

    pack_link = utils.name2link(pack_name)

    # we edit this flag so the 'finally' statement can end the conversation if needed by an 'except'
    end_conversation = False
    try:
        logger.debug('executing request...')
        request_payload = {
            "user_id": update.effective_user.id,
            "name": pack_name,
            "emojis": sticker_file.get_emojis_str(),
            sticker_file.api_arg_name: sticker_file.get_input_file(),
            "mask_position": None
        }
        send_request(context.bot.add_sticker_to_set, request_payload)
    except error.PackFull:
        max_pack_size = MAX_PACK_SIZE.get(sticker_file.type, 0)
        update.message.reply_html(Strings.ADD_STICKER_PACK_FULL.format(pack_link, max_pack_size), quote=True)

        end_conversation = True  # end the conversation when a pack is full
    except error.FileDimensionInvalid:
        logger.error('resized stickers has the wrong size: %s', str(sticker_file))
        update.message.reply_html(Strings.ADD_STICKER_SIZE_ERROR, quote=True)
    except error.InvalidAnimatedSticker:
        update.message.reply_html(Strings.ADD_STICKER_INVALID_ANIMATED, quote=True)
    except error.PackInvalid:
        # pack name invalid or that pack has been deleted: delete it from the db
        with session_scope() as session:
            deleted_rows = session.query(Pack).filter(Pack.user_id == update.effective_user.id,
                                                      Pack.name == pack_name).delete('fetch')
            logger.debug('rows deleted: %d', deleted_rows or 0)

            # get the remaining packs' titles
            pack_titles = [t.title for t in session.query(Pack.title).filter_by(user_id=update.effective_user.id).order_by(Pack.title).all()]

        if not pack_titles:
            # user doesn't have any other pack to chose from, reset his status
            update.message.reply_html(Strings.ADD_STICKER_PACK_NOT_VALID_NO_PACKS.format(pack_link))

            logger.debug('calling stickers.close()...')
            sticker_file.close()
            return ConversationHandler.END
        else:
            # make the user select another pack from the keyboard
            markup = Keyboard.from_list(pack_titles)
            update.message.reply_html(Strings.ADD_STICKER_PACK_NOT_VALID.format(pack_link), reply_markup=markup)
            context.user_data['pack'].pop('name', None)  # remove temporary data

            logger.debug('calling stickers.close()...')
            sticker_file.close()
            return Status.ADD_WAITING_TITLE
    except error.UnknwonError as e:
        update.message.reply_html(Strings.ADD_STICKER_GENERIC_ERROR.format(pack_link, e.message), quote=True)
    except Exception as e:
        logger.error('non-telegram exception while adding a stickers to a set', exc_info=True)
        raise e  # this is not raised
    else:
        text = Strings.ADD_STICKER_SUCCESS_EMOJIS.format(pack_link, sticker_file.get_emojis_str())
        update.message.reply_html(text, quote=True)
    finally:
        # this is entered even when we enter the 'else' or we return in an 'except'
        # https://stackoverflow.com/a/19805746
        logger.debug('calling stickers.close()...')
        sticker_file.close()

        if end_conversation:
            return ConversationHandler.END

        return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_sticker_receive(update: Update, context: CallbackContext):
    logger.info('user sent a stickers to add')
    logger.debug('user_data: %s', context.user_data)

    sticker_file = StickerFile(update.message)
    if context.user_data["pack"]["pack_type"] != sticker_file.type:
        type_received = STICKER_TYPE_DESC.get(sticker_file.type, "-unknown-")
        type_expected = STICKER_TYPE_DESC.get(context.user_data["pack"]["pack_type"], "-unknown-")
        update.message.reply_html(Strings.ADD_STICKER_EXPECTING_DIFFERENT_TYPE.format(type_expected, type_received))
        return Status.WAITING_STICKER

    return add_sticker_to_set(update, context)


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_text_receive(update: Update, context: CallbackContext):
    logger.info('user sent a text message while we were waiting for a stickers')
    logger.debug('user_data: %s', context.user_data)

    emojis = utils.get_emojis(update.message.text, as_list=True)
    if not emojis:
        update.message.reply_text(Strings.ADD_STICKER_NO_EMOJI_IN_TEXT)
        return Status.WAITING_STICKER
    elif len(emojis) > 10:
        update.message.reply_text(Strings.ADD_STICKER_TOO_MANY_EMOJIS)
        return Status.WAITING_STICKER

    context.user_data['pack']['emojis'] = emojis

    update.message.reply_text(Strings.ADD_STICKER_EMOJIS_SAVED.format(
        len(emojis),
        ''.join(emojis)
    ))

    return Status.WAITING_STICKER


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_title_invalid_message(update: Update, _):
    logger.info('(add) waiting title: wrong type of message received')

    update.message.reply_html(Strings.PACK_TITLE_INVALID_MESSAGE)

    return Status.ADD_WAITING_TITLE


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_name_invalid_message(update: Update, _):
    logger.info('(add) waiting name: wrong type of message received')

    update.message.reply_html(Strings.PACK_NAME_INVALID_MESSAGE)

    return Status.ADD_WAITING_NAME


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_waiting_sticker_invalid_message(update: Update, context: CallbackContext):
    logger.info('(add) waiting stickers: wrong type of message received')

    update.message.reply_html(Strings.ADD_STICKER_INVALID_MESSAGE)

    return Status.WAITING_STICKER

