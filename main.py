import time
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice
from config import BOT_TOKEN, API_URL, WEB_APP_URL

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

def get_user_attr(user_id, key, default=None):
    return user_data.get(user_id, {}).get(key, default)

def set_user_attr(user_id, key, value):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id][key] = value

@bot.message_handler(commands=['start'])
def send_start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌐 Change Language", callback_data="/btn_lang"))
    bot.send_message(message.chat.id, "🎬 Welcome to TikTok Downloader Bot!\n\nSend any TikTok link below to start.", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text and ('tiktok.com' in msg.text.lower() or 'vt.tiktok.com' in msg.text.lower()))
def handle_tiktok_link(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "tiktok_url", message.text.strip())
    
    expiry_time = get_user_attr(u_id, "ad_pass_expiry", 0)
    if current_time < expiry_time:
        send_quality_options(message.chat.id)
        return

    gate_msg = "To continue, watch a short ad (5 sec) or buy /premium"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("👉 Watch ad", web_app=WebAppInfo(url=WEB_APP_URL)))
    markup.add(InlineKeyboardButton("Buy Premium", callback_data="/buy_premium"))
    markup.add(InlineKeyboardButton("Skip", callback_data="/skip_ad"))

    bot.send_message(message.chat.id, gate_msg, reply_markup=markup)

@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "ad_pass_expiry", current_time + 86400)
    bot.send_message(message.chat.id, "✅ Ad verified successfully!")
    send_quality_options(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == '/skip_ad')
def handle_skip(call):
    u_id = call.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "ad_pass_expiry", current_time + 86400)
    bot.answer_callback_query(call.id, "Skipped ad!")
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎬 Video (No Watermark)", callback_data="quality_nowatermark"),
        InlineKeyboardButton("🎵 Audio (MP3)", callback_data="quality_audio")
    )
    bot.edit_message_text("🎥 Choose download option:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def send_quality_options(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎬 Video (No Watermark)", callback_data="quality_nowatermark"),
        InlineKeyboardButton("🎵 Audio (MP3)", callback_data="quality_audio")
    )
    bot.send_message(chat_id, "🎥 Choose download option:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_download(call):
    u_id = call.from_user.id
    quality = call.data.replace('quality_', '')
    url = get_user_attr(u_id, "tiktok_url")

    if not url:
        bot.edit_message_text("❌ Session expired. Send the TikTok link again.", call.message.chat.id, call.message.message_id)
        return

    bot.edit_message_text("⏳ Processing your request...", call.message.chat.id, call.message.message_id)

    try:
        resp = requests.get(f"{API_URL}?url={url}", timeout=15)
        data = resp.json()

        if data.get('success'):
            result = data.get('result', [{}])[0]
            download_url = None

            if quality == 'audio':
                music_info = result.get('music', {})
                download_url = music_info.get('play_url') if isinstance(music_info, dict) else result.get('audio')
            else:
                videos = result.get('videos', [])
                if videos:
                    download_url = videos[0].get('url')

            if download_url:
                if quality == 'audio':
                    bot.send_audio(call.message.chat.id, audio=download_url, title="TikTok Audio")
                else:
                    bot.send_video(call.message.chat.id, video=download_url)
                bot.delete_message(call.message.chat.id, call.message.message_id)
            else:
                bot.edit_message_text("❌ Could not extract download link.", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text("❌ API Error. Try another link.", call.message.chat.id, call.message.message_id)
    except Exception:
        bot.edit_message_text("❌ Connection error. Try again.", call.message.chat.id, call.message.message_id)

bot.infinity_polling()
