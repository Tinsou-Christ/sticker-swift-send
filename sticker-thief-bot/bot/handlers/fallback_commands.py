import logging

# noinspection PyPackageRequirements
from telegram import Update, ChatAction
# noinspection PyPackageRequirements
from telegram.ext import ConversationHandler, CallbackContext

from bot.markups import Keyboard
from bot.strings import Strings
from ..utils import decorators
from ..utils import utils

logger = logging.getLogger(__name__)

# keys we have to try to pop from user_data
USER_DATA_KEYS_TO_POP = ("pack", "crop", "ignore_rateo", "png")


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
@decorators.logconversation
def cancel_command(update: Update, context: CallbackContext):
    logger.info('%s command', update.message.text)

    update.message.reply_text(Strings.CANCEL, reply_markup=Keyboard.HIDE)

    utils.user_data_cleanup(context)
    
    return ConversationHandler.END


@decorators.action(ChatAction.TYPING)
@decorators.failwithmessage
@decorators.logconversation
def on_timeout(update: Update, context: CallbackContext):
    logger.debug('conversation timeout')

    utils.user_data_cleanup(context)

    update.message.reply_text(Strings.TIMEOUT, reply_markup=Keyboard.HIDE, disable_notification=True)

    return ConversationHandler.END
