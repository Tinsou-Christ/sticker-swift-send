import logging
import os
import re
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

# noinspection PyPackageRequirements
import requests
# noinspection PyPackageRequirements
from telegram import ChatAction, Update
# noinspection PyPackageRequirements
from telegram.ext import CommandHandler, CallbackContext

from bot import stickersbot
from bot.utils import decorators

logger = logging.getLogger(__name__)

API_ENDPOINT = "https://shizuai.vercel.app/chat"
CLEAR_ENDPOINT = "https://shizuai.vercel.app/chat/clear"


def to_sans_serif(text: str) -> str:
    """convertit le texte en police mathematical sans-serif unicode (𝖺𝖠𝗓𝖹)"""
    if not text:
        return text

    result = []
    for ch in text:
        if 'A' <= ch <= 'Z':
            result.append(chr(0x1D5A0 + (ord(ch) - ord('A'))))
        elif 'a' <= ch <= 'z':
            result.append(chr(0x1D5BA + (ord(ch) - ord('a'))))
        elif '0' <= ch <= '9':
            result.append(chr(0x1D7E2 + (ord(ch) - ord('0'))))
        else:
            result.append(ch)
    return ''.join(result)


def normalize_text(text: str) -> str:
    """supprime les references a l'auteur original de l'API et les remplace par Christus"""
    if not text:
        return text

    text = re.sub(r'Aryan\s*Chauchan', 'Christus', text, flags=re.I)
    text = re.sub(r'Aryan\s*Chauhan', 'Christus', text, flags=re.I)
    text = re.sub(r'A\.?\s*Chauchan', 'Christus', text, flags=re.I)
    return text


def download_to_tempfile(url: str, extension: str) -> str:
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    fd, path = tempfile.mkstemp(suffix='.{}'.format(extension))
    with os.fdopen(fd, 'wb') as f:
        f.write(response.content)

    return path


def get_largest_photo_url(context: CallbackContext, photo_sizes) -> str:
    file_id = photo_sizes[-1].file_id  # plus grande resolution
    file = context.bot.get_file(file_id)
    return file.file_path


@decorators.action(ChatAction.TYPING)
@decorators.restricted
@decorators.failwithmessage
def on_ai_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    input_text = ' '.join(context.args).strip()

    # reset de la conversation
    if input_text.lower() in ('reset', 'clear'):
        try:
            requests.delete('{}/{}'.format(CLEAR_ENDPOINT, user_id), timeout=15)
            update.message.reply_text('♻️ Conversation reset successfully.')
        except Exception:
            update.message.reply_text('❌ Failed to reset conversation.')
        return

    # recherche d'une image dans le message actuel ou dans le message auquel on repond
    image_url = None
    try:
        if update.message.photo:
            image_url = get_largest_photo_url(context, update.message.photo)
        elif update.message.reply_to_message and update.message.reply_to_message.photo:
            image_url = get_largest_photo_url(context, update.message.reply_to_message.photo)
    except Exception as e:
        logger.error('failed to get photo url: %s', str(e))

    if not input_text and not image_url:
        update.message.reply_text('💬 Please provide a message or an image.')
        return

    timestamp = datetime.now(ZoneInfo('Asia/Manila')).strftime('%B %d, %Y %I:%M %p')

    wait_message = update.message.reply_text(
        '🤖 AI is thinking...\n━━━━━━━━━━━━━━━\n📅 {}'.format(timestamp)
    )

    created_files = []

    try:
        response = requests.post(
            API_ENDPOINT,
            json={
                'uid': user_id,
                'message': input_text or '',
                'image_url': image_url
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()

        reply_text = data.get('reply') or '✅ AI Response'
        text = normalize_text(reply_text).replace('*', '')
        text = to_sans_serif(text)

        image_data = data.get('image_url')
        music_data = data.get('music_data') or {}
        video_data = data.get('video_data') or {}
        shoti_data = data.get('shoti_data') or {}
        lyrics_data = data.get('lyrics_data') or {}

        attachments = []

        if image_data:
            path = download_to_tempfile(image_data, 'jpg')
            attachments.append(('photo', path))
            created_files.append(path)

        if music_data.get('downloadUrl'):
            path = download_to_tempfile(music_data['downloadUrl'], 'mp3')
            attachments.append(('audio', path))
            created_files.append(path)

        video_url = video_data.get('downloadUrl') or shoti_data.get('downloadUrl')
        if video_url:
            path = download_to_tempfile(video_url, 'mp4')
            attachments.append(('video', path))
            created_files.append(path)

        if lyrics_data.get('lyrics'):
            lyrics = normalize_text(lyrics_data['lyrics'][:1500]).replace('*', '')
            lyrics = to_sans_serif(lyrics)
            track_name = to_sans_serif(lyrics_data.get('track_name', ''))
            text += '\n\n🎵 {}\n{}'.format(track_name, lyrics)

        context.bot.delete_message(update.effective_chat.id, wait_message.message_id)

        if attachments:
            for media_type, path in attachments:
                with open(path, 'rb') as f:
                    if media_type == 'photo':
                        update.message.reply_photo(f, caption=text)
                    elif media_type == 'audio':
                        update.message.reply_audio(f, caption=text)
                    else:
                        update.message.reply_video(f, caption=text)
        else:
            update.message.reply_text(text)

    except Exception as e:
        logger.error('AI command error: %s', str(e), exc_info=True)
        context.bot.edit_message_text(
            '❌ An AI error occurred.',
            chat_id=update.effective_chat.id,
            message_id=wait_message.message_id
        )
    finally:
        for path in created_files:
            if os.path.exists(path):
                os.remove(path)


stickersbot.add_handler(CommandHandler('ai', on_ai_command))
stickersbot.add_handler(CommandHandler('shizu', on_ai_command))  # alias, comme dans le fichier JS original
