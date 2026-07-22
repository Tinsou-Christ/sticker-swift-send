import logging
import time

# noinspection PyPackageRequirements
from telegram.ext import CallbackContext, CommandHandler
# noinspection PyPackageRequirements
from telegram import ChatAction, Update
# noinspection PyPackageRequirements
from telegram.error import Unauthorized, BadRequest
from sqlalchemy import func

from bot import stickersbot
from bot.utils import decorators
from bot.database.models.admin import Admin
from bot.database.models.user import User
from bot.database.models.pack import Pack
from bot.database.base import session_scope
from config import config

logger = logging.getLogger(__name__)


@decorators.action(ChatAction.TYPING)
@decorators.adminsonly
@decorators.failwithmessage
def on_addadmin_command(update: Update, context: CallbackContext):
    logger.info('/addadmin')

    if not context.args:
        update.message.reply_text('Usage: /addadmin <user_id>')
        return

    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        update.message.reply_text('The user_id must be a number')
        return

    Admin.add(new_admin_id, added_by=update.effective_user.id)
    update.message.reply_text('User {} is now an admin ✅'.format(new_admin_id))


@decorators.action(ChatAction.TYPING)
@decorators.adminsonly
@decorators.failwithmessage
def on_removeadmin_command(update: Update, context: CallbackContext):
    logger.info('/removeadmin')

    if not context.args:
        update.message.reply_text('Usage: /removeadmin <user_id>')
        return

    try:
        admin_id = int(context.args[0])
    except ValueError:
        update.message.reply_text('The user_id must be a number')
        return

    if admin_id in config.telegram.admins:
        update.message.reply_text("This admin is set in the config file, it can't be removed from here")
        return

    Admin.remove(admin_id)
    update.message.reply_text('User {} is no longer an admin ❌'.format(admin_id))


@decorators.action(ChatAction.TYPING)
@decorators.adminsonly
@decorators.failwithmessage
def on_listadmins_command(update: Update, context: CallbackContext):
    logger.info('/listadmins')

    all_admins = set(config.telegram.admins) | set(Admin.all_ids())

    text = '👑 <b>Admins</b>\n' + '\n'.join('• <code>{}</code>'.format(a) for a in all_admins)
    update.message.reply_html(text)


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
def on_leaderboard_command(update: Update, context: CallbackContext):
    logger.info('/leaderboard')

    with session_scope() as session:
        results = (
            session.query(Pack.user_id, func.count(Pack.pack_id).label('packs_count'))
            .group_by(Pack.user_id)
            .order_by(func.count(Pack.pack_id).desc())
            .limit(10)
            .all()
        )

        if not results:
            update.message.reply_text('No data yet!')
            return

        text = '🏆 <b>Leaderboard</b> — top pack creators\n\n'
        medals = ['🥇', '🥈', '🥉']
        for i, (user_id, packs_count) in enumerate(results):
            prefix = medals[i] if i < 3 else '{}.'.format(i + 1)
            text += '{} <code>{}</code> — {} pack(s)\n'.format(prefix, user_id, packs_count)

    update.message.reply_html(text)


@decorators.action(ChatAction.TYPING)
@decorators.adminsonly
@decorators.failwithmessage
def on_broadcast_command(update: Update, context: CallbackContext):
    logger.info('/broadcast')

    is_reply_broadcast = bool(update.message.reply_to_message)

    if not is_reply_broadcast and not context.args:
        update.message.reply_text(
            'Usage: /broadcast <message>, or reply to a message with /broadcast to forward it to everyone'
        )
        return

    text_to_send = ' '.join(context.args) if context.args else None

    with session_scope() as session:
        all_users = [row.user_id for row in session.query(User).all()]

    update.message.reply_text('Starting broadcast to {} user(s)...'.format(len(all_users)))

    sent = 0
    blocked = 0
    failed = 0

    for user_id in all_users:
        try:
            if is_reply_broadcast:
                context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.reply_to_message.message_id
                )
            else:
                context.bot.send_message(chat_id=user_id, text=text_to_send)
            sent += 1
        except Unauthorized:
            blocked += 1
        except BadRequest as e:
            logger.warning('broadcast BadRequest for %d: %s', user_id, str(e))
            failed += 1
        except Exception as e:
            logger.error('error broadcasting to %d: %s', user_id, str(e))
            failed += 1

        time.sleep(0.05)  # évite de dépasser les limites anti-flood de Telegram

    update.message.reply_text(
        'Broadcast completed ✅\nSent: {}\nBlocked bot: {}\nFailed: {}'.format(sent, blocked, failed)
    )


stickersbot.add_handler(CommandHandler('addadmin', on_addadmin_command))
stickersbot.add_handler(CommandHandler('removeadmin', on_removeadmin_command))
stickersbot.add_handler(CommandHandler('listadmins', on_listadmins_command))
stickersbot.add_handler(CommandHandler('leaderboard', on_leaderboard_command))
stickersbot.add_handler(CommandHandler('broadcast', on_broadcast_command))
