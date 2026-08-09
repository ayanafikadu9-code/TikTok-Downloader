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
    u_id = message.from_user.id
    lang = get_user_attr(u_id, "lang", "en")
    
    if lang == "am":
        text_msg = "🎬 እንኳን ወደ TikTok ማውረጃ በደህና መጡ!\n\nቪዲዮ ለማውረድ የ TikTok ሊንክ ይላኩ።"
        btn_lang = "🌐 ቋንቋ ለመቀየር"
    else:
        text_msg = "🎬 Welcome to TikTok Downloader Bot!\n\nSend any TikTok link below to start."
        btn_lang = "🌐 Change Language"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(btn_lang, callback_data="/btn_lang"))
    bot.send_message(message.chat.id, text_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['/btn_lang', '/lang_en', '/lang_am', '/btn_home'])
def handle_language(call):
    u_id = call.from_user.id
    if call.data == '/btn_home':
        send_start(call.message)
        return

    if call.data == '/btn_lang':
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("🇬🇧 English", callback_data="/lang_en"),
            InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="/lang_am")
        )
        markup.row(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        bot.edit_message_text("🌐 Please select your language / ቋንቋ ይምረጡ:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    else:
        selected_lang = call.data.replace('/lang_', '')
        set_user_attr(u_id, "lang", selected_lang)
        confirm_text = "✅ Language updated successfully.\n\nNow send your TikTok link."
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        bot.edit_message_text(confirm_text, call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text and ('tiktok.com' in msg.text.lower() or 'vt.tiktok.com' in msg.text.lower()))
def handle_tiktok_link(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "tiktok_url", message.text.strip())
    
    # Reset ad watch flag for this new link
    set_user_attr(u_id, "watched_ad", False)
    
    expiry_time = get_user_attr(u_id, "ad_pass_expiry", 0)
    if current_time < expiry_time:
        send_quality_options(message.chat.id, get_user_attr(u_id, "lang", "en"))
        return

    gate_msg = "🔥 10,000 ቪዲዮዎችን በነፃ ለማውረድ ማስታወቂያውን ይዩ:\n\n1️⃣ ማስታወቂያ ይመልከቱ (15 ሰከንድ)\n2️⃣ ማስታወቂያ ተመልክቻለሁ የሚለውን ይጫኑ"
    
    markup = InlineKeyboardMarkup()
    # Red button for watching ad
    markup.add(InlineKeyboardButton("👁️ ማስታወቂያ ይመልከቱ (15s)", web_app=WebAppInfo(url=WEB_APP_URL), style="danger"))
    # Green button for verifying
    markup.add(InlineKeyboardButton("✅ ማስታወቂያ ተመልክቻለሁ", callback_data="/verify_ad", style="success"))
    # Blue/Primary button for premium
    markup.add(InlineKeyboardButton("⭐ ፕሪሚየም ይግዙ", callback_data="/buy_premium", style="primary"))
    # Red button for main menu
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    bot.send_message(message.chat.id, gate_msg, reply_markup=markup)

@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    u_id = message.from_user.id
    # Automatically mark as watched when they complete the WebApp countdown
    set_user_attr(u_id, "watched_ad", True)

@bot.callback_query_handler(func=lambda call: call.data == '/verify_ad')
def handle_verify_ad(call):
    u_id = call.from_user.id
    lang = get_user_attr(u_id, "lang", "en")
    
    # Check if they actually triggered the webapp view or finished the timer
    watched = get_user_attr(u_id, "watched_ad", False)
    if not watched:
        bot.answer_callback_query(call.id, "⚠️ እባክዎ በመጀመሪያ የ 15 ሰከንድ ማስታወቂያ ይዩ!", show_alert=True)
        return

    current_time = int(time.time())
    set_user_attr(u_id, "ad_pass_expiry", current_time + 86400)
    
    bot.answer_callback_query(call.id, "✅ Ad verified successfully!")
    send_quality_options(call.message.chat.id, lang, call.message.message_id, edit=True)

def send_quality_options(chat_id, lang, message_id=None, edit=False):
    if lang == "am":
        prompt_text = "🎥 የማውረድ አማራጭ ይምረጡ:"
        b_no_wm, b_wm, b_au = "🎬 ቪዲዮ (ያለ ዋተርማርክ)", "🏷️ ቪዲዮ (ከዋተርማርክ ጋር)", "🎵 ድምፅ ብቻ (MP3)"
    else:
        prompt_text = "🎥 Choose download option:"
        b_no_wm, b_wm, b_au = "🎬 Video (No Watermark)", "🏷️ Video (With Watermark)", "🎵 Audio Only (MP3)"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(b_no_wm, callback_data="quality_nowatermark", style="success"))
    markup.add(InlineKeyboardButton(b_wm, callback_data="quality_watermark", style="primary"))
    markup.add(InlineKeyboardButton(b_au, callback_data="quality_audio", style="primary"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    if edit and message_id:
        bot.edit_message_text(prompt_text, chat_id, message_id, reply_markup=markup)
    else:
        bot.send_message(chat_id, prompt_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == '/buy_premium')
def handle_premium_menu(call):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚫 1 month — 50 ⭐️", callback_data="buy_stars_50", style="primary"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))
    
    bot.edit_message_text("⭐ Unlock unlimited ad-free downloads with Telegram Stars.", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_stars_'))
def send_star_invoice(call):
    stars = int(call.data.split('_')[2])
    bot.send_invoice(
        call.message.chat.id,
        title="TikTok Downloader Premium",
        description="Unlock 30 days of ad-free downloads.",
        payload=f"premium_30_{call.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium", amount=stars)],
        start_parameter="premium"
    )

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    u_id = message.from_user.id
    set_user_attr(u_id, "ad_pass_expiry", int(time.time()) + 86400)
    bot.send_message(message.chat.id, "🎉 Payment received! Premium activated for 24 hours.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_download(call):
    u_id = call.from_user.id
    quality = call.data.replace('quality_', '')
    url = get_user_attr(u_id, "tiktok_url")

    if not url:
        bot.edit_message_text("❌ Session expired. Send the link again.", call.message.chat.id, call.message.message_id)
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
                download_url = music_info.get('play_url') or result.get('audio')
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

print("Bot running with secure color buttons...")
bot.infinity_polling()
