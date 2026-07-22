import json
import logging
import logging.config
import os
import pickle
from html import escape
from pickle import UnpicklingError

import emoji
# noinspection PyPackageRequirements
from telegram import Message, Sticker, StickerSet
# noinspection PyPackageRequirements
from telegram.ext import PicklePersistence, CallbackContext

from constants.data import TemporaryKeys

logger = logging.getLogger(__name__)


def load_logging_config(file_name='logging.json'):
    with open(file_name, 'r') as f:
        logging_config = json.load(f)

    logging.config.dictConfig(logging_config)


def escape_html(*args, **kwargs):
    return escape(*args, **kwargs)


def name2link(name: str, bot_username=None):
    if bot_username and not name.endswith('_by_' + bot_username):
        name += '_by_' + bot_username

    return 'https://t.me/addstickers/{}'.format(name)


def sticker2link(sticker: Sticker, bot_username=None):
    if not sticker.set_name:
        raise ValueError("<Sticker> object doesn not belong to a pack")

    return name2link(sticker.set_name, bot_username)


def stickerset_title_link(sticker_set: StickerSet):
    return f'<a href="{name2link(sticker_set.name)}">{escape_html(sticker_set.title)}</a>'


def get_emojis(text, as_list=False):
    emojis = [e["emoji"] for e in emoji.emoji_list(text)]
    if as_list:
        return emojis
    else:
        return ''.join(emojis)


def get_emojis_from_message(message: Message) -> [list, None]:
    """Will return a list: either the stickers's emoji (in a list) or the emojis in the document's caption. Will
    return None if the document's caption doesn't have any emoji"""

    if message.sticker:
        if message.sticker.emoji:
            return [message.sticker.emoji]
        else:
            # the stickers doesn't have a pack -> no emoji
            return None
    elif message.document and not message.caption:
        return None
    elif message.document and message.caption:
        emojis_list = get_emojis(message.caption, as_list=True)
        if not emojis_list:
            return None

        return emojis_list


def persistence_object(config_enabled=True, file_path='persistence/data.pickle'):
    if not config_enabled:
        return

    logger.info('unpickling persistence: %s', file_path)
    try:
        # try to load the file
        try:
            with open(file_path, "rb") as f:
                pickle.load(f)
        except FileNotFoundError:
            pass

    except (UnpicklingError, EOFError):
        logger.warning('deserialization failed: removing persistence file and trying again')
        os.remove(file_path)

    return PicklePersistence(
        filename=file_path,
        store_chat_data=False,
        store_bot_data=False
    )


def debug_print_image(image_data_bw):
    # will print the image with X and O
    test_string = ""
    for column in image_data_bw:
        for row in column:
            test_string += "░" if row == 255 else "█"
        test_string += "\n"
    print(test_string)


def check_flags(options, context: CallbackContext, pop_existing_flags=True):
    if pop_existing_flags:
        # remove all flags before checking if there are some enabled
        for option_key, (user_data_key, _) in options.items():
            context.user_data.pop(user_data_key, None)

    if not context.args:
        return []

    enabled_options_description = []
    for option_key, (user_data_key, description) in options.items():
        if option_key in context.args:
            context.user_data[user_data_key] = True
            enabled_options_description.append(description)

    return enabled_options_description


def user_data_cleanup(context: CallbackContext):
    for key in TemporaryKeys.USER_DATA:
        context.user_data.pop(key, None)
