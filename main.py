import time
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice

# ============ CONFIGURATION ============
BOT_TOKEN = "8913902406:AAE5YB6XyXY4JBXbODODwOTl4P-dnV7T2rA"
API_URL = "https://silent-mud-7026.codeofsaladin.workers.dev/tiktok"
WEB_APP_URL = "https://ayanafikadu9-code.github.io/TikTok-Downloader/"

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

def get_user_attr(user_id, key, default=None):
    return user_data.get(user_id, {}).get(key, default)

def set_user_attr(user_id, key, value):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id][key] = value

# ----------------------------------------------------
# 1. COMMAND: /start
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_start(message):
    u_id = message.from_user.id
    lang = get_user_attr(u_id, "lang", "en")

    if lang == "am":
        text_msg = "🎬 **እንኳን ወደ TikTok ማውረጃ በደህና መጡ!**\n\nቪዲዮ ለማውረድ የ TikTok ሊንክ ይላኩ።"
        btn_lang = "🌐 ቋንቋ ለመቀየር"
    elif lang == "om":
        text_msg = "🎬 **Baga gara Buufata TikTok Nageenyaan Dhuftan!**\n\nViidiyoo buufachuuf hidhaa TikTok ergaa."
        btn_lang = "🌐 Afaan Jijjiiruuf"
    else:
        text_msg = "🎬 **Welcome to TikTok Downloader Bot!**\n\nSend any TikTok link below to start."
        btn_lang = "🌐 Change Language"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(btn_lang, callback_data="/btn_lang"))
    bot.send_message(message.chat.id, text_msg, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# 2. LANGUAGE SELECTION MENU
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data in ['/btn_lang', '/lang_en', '/lang_am', '/lang_om'])
def handle_language(call):
    u_id = call.from_user.id
    if call.data == '/btn_lang':
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("🇬🇧 English", callback_data="/lang_en"),
            InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="/lang_am")
        )
        markup.row(InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="/lang_om"))
        markup.row(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        bot.edit_message_text("🌐 **Please select your language / ቋንቋ ይምረጡ / Afaan filadhaa:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        selected_lang = call.data.replace('/lang_', '')
        set_user_attr(u_id, "lang", selected_lang)
        confirm_text = "✅ Language set to **English**."
        if selected_lang == "am":
            confirm_text = "✅ ቋንቋው በሁኔታው ወደ **አማርኛ** ተቀይሯል።"
        elif selected_lang == "om":
            confirm_text = "✅ Afaan gara **Afaan Oromotti** jijjiirameera."

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        bot.edit_message_text(confirm_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# 3. LINK DETECTION (AD GATE & PREMIUM MENU)
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: 'tiktok.com' in msg.text.lower() or 'vt.tiktok.com' in msg.text.lower())
def handle_tiktok_link(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "tiktok_url", message.text.strip())
    
    lang = get_user_attr(u_id, "lang", "en")
    expiry_time = get_user_attr(u_id, "ad_pass_expiry", 0)
    has_active_pass = current_time < expiry_time

    if not has_active_pass:
        if lang == "am":
            gate_msg = "🔥 **ቪዲዮ ለማውረድ ማስታወቂያ ይመልከቱ ወይም ፕሪሚየም ይግዙ:**"
            b_ad, b_prem = "👁️ ማስታወቂያ ይመልከቱ (10s)", "⭐ ፕሪሚየም ይግዙ (Telegram Stars)"
        elif lang == "om":
            gate_msg = "🔥 **Viidiyoo buufachuuf beeksisa daawwadhaa ykn piriimiyamii bitaa:**"
            b_ad, b_prem = "👁️ Beeksisa Daawwadhaa (10s)", "⭐ Piriimiyamii Bitaa (Telegram Stars)"
        else:
            gate_msg = "🔥 **To continue, watch a short ad or buy Premium:**"
            b_ad, b_prem = "👉 Watch ad", "⭐ Buy Premium"

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(b_ad, web_app=WebAppInfo(url=WEB_APP_URL)))
        markup.add(InlineKeyboardButton(b_prem, callback_data="/buy_premium"))
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))

        bot.send_message(message.chat.id, gate_msg, reply_markup=markup, parse_mode="Markdown")
    else:
        send_quality_options(message.chat.id, lang)

def send_quality_options(chat_id, lang):
    if lang == "am":
        prompt_text = "🎥 **የማውረድ አማራጭ ይምረጡ:**"
        b_no_wm, b_wm, b_au = "🎬 ቪዲዮ (ያለ ዋተርማርክ)", "🏷️ ቪዲዮ (ከዋተርማርክ ጋር)", "🎵 ድምፅ ብቻ (MP3)"
    elif lang == "om":
        prompt_text = "🎥 **Filannoo buufata filadhaa:**"
        b_no_wm, b_wm, b_au = "🎬 Viidiyoo (Mallattoo Malee)", "🏷️ Viidiyoo (Mallattoo Wajjin)", "🎵 Sagalee Qofa (MP3)"
    else:
        prompt_text = "🎥 **Choose download option:**"
        b_no_wm, b_wm, b_au = "🎬 Video (No Watermark)", "🏷️ Video (With Watermark)", "🎵 Audio Only (MP3)"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(b_no_wm, callback_data="quality_nowatermark"))
    markup.add(InlineKeyboardButton(b_wm, callback_data="quality_watermark"))
    markup.add(InlineKeyboardButton(b_au, callback_data="quality_audio"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))

    bot.send_message(chat_id, prompt_text, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# 4. WEB APP AD COMPLETION CALLBACK
# ----------------------------------------------------
@bot.message_handler(content_types=['web_app_data'])
def handle_ad_completion(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    
    if message.web_app_data.data == "AD_COMPLETED":
        set_user_attr(u_id, "ad_pass_expiry", current_time + 86400)
        
        lang = get_user_attr(u_id, "lang", "en")
        bot.send_message(message.chat.id, "✅ **Ad verified! 24-Hour Pass Unlocked.**")
        send_quality_options(message.chat.id, lang)

# ----------------------------------------------------
# 5. TELEGRAM STARS PREMIUM MENU & INVOICING (30% DISCOUNT)
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data in ['/buy_premium', '/btn_home'])
def handle_premium_menu(call):
    u_id = call.from_user.id
    if call.data == '/btn_home':
        send_start(call.message)
        return

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚫 1 month — 50 ⭐️ (30% OFF)", callback_data="buy_stars_50"))
    markup.add(InlineKeyboardButton("🔥 3 months — 105 ⭐️ (30% OFF)", callback_data="buy_stars_105"))
    markup.add(InlineKeyboardButton("💎 12 months — 350 ⭐️ (30% OFF)", callback_data="buy_stars_350"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))

    msg = (
        "🚫 **Remove ads**\n\n"
        "Download videos without mandatory ads or waiting.\n\n"
        "**Premium includes:**\n"
        "✅ No ads before downloads\n"
        "✅ High-speed direct servers\n"
        "✅ Priority support\n\n"
        "Choose how long to remove ads 👇"
    )
    bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_stars_'))
def send_star_invoice(call):
    stars = int(call.data.split('_')[2])
    days_map = {50: 30, 105: 90, 350: 365}
    days = days_map.get(stars, 30)

    title = "TikTok Downloader Premium"
    description = f"Unlock {days} days of ad-free unlimited TikTok downloads."
    payload = f"premium_{days}_{call.from_user.id}"
    currency = "XTR"  # XTR is the official code for Telegram Stars
    prices = [LabeledPrice(label=f"Premium ({days} Days)", amount=stars)]

    bot.send_invoice(
        call.message.chat.id,
        title=title,
        description=description,
        invoice_payload=payload,
        provider_token="",  # Must remain empty for Telegram Stars
        currency=currency,
        prices=prices,
        start_parameter="premium-subscription"
    )

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    
    payload = message.successful_payment.invoice_payload
    days = int(payload.split('_')[1])
    
    expiry = current_time + (days * 86400)
    set_user_attr(u_id, "ad_pass_expiry", expiry)

    bot.send_message(
        message.chat.id, 
        f"🎉 **Payment Received!**\n\nYour Premium Subscription is now active for **{days} days**. Enjoy ad-free downloading!",
        parse_mode="Markdown"
    )

# ----------------------------------------------------
# 6. EXECUTE DOWNLOAD (DIRECT TELEGRAM STREAMING)
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_download(call):
    u_id = call.from_user.id
    quality = call.data.replace('quality_', '')
    url = get_user_attr(u_id, "tiktok_url")

    if not url:
        bot.edit_message_text("❌ Session expired. Please send the TikTok link again.", call.message.chat.id, call.message.message_id)
        return

    bot.edit_message_text("⏳ **Processing your request...**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    try:
        resp = requests.get(f"{API_URL}?url={url}", timeout=15)
        data = resp.json()

        if data.get('success'):
            result = data.get('result', [{}])[0]
            download_url = None

            if quality == 'audio':
                music_info = result.get('music', {})
                if isinstance(music_info, dict):
                    download_url = music_info.get('play_url') or music_info.get('url')
                elif isinstance(music_info, list) and len(music_info) > 0:
                    download_url = music_info[0].get('play_url') or music_info[0].get('url')
                if not download_url:
                    download_url = result.get('audio')
            else:
                videos = result.get('videos', [])
                if videos:
                    if quality == 'watermark':
                        for v in videos:
                            if 'watermark' in v.get('quality', '').lower():
                                download_url = v.get('url')
                                break
                        if not download_url:
                            download_url = videos[0].get('url')
                    else:
                        download_url = videos[0].get('url')

            if download_url:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))

                if quality == 'audio':
                    bot.send_audio(
                        call.message.chat.id, 
                        audio=download_url, 
                        title="TikTok Audio Stream", 
                        performer="MakeChapa Bot"
                    )
                else:
                    bot.send_video(
                        call.message.chat.id, 
                        video=download_url
                    )

                bot.edit_message_text("✅ **Download Complete!**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.edit_message_text("❌ Could not extract download link.", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text("❌ API Error. Please try a different TikTok link.", call.message.chat.id, call.message.message_id)
    except Exception:
        bot.edit_message_text("❌ Connection error while downloading. Try again.", call.message.chat.id, call.message.message_id)

print("Bot is starting...")
bot.infinity_polling()
