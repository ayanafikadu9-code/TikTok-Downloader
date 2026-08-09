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

# ----------------------------------------------------
# 1. /START & LANGUAGE SELECTION
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_start(message):
    u_id = message.from_user.id
    lang = get_user_attr(u_id, "lang", "en")

    if lang == "am":
        text_msg = "🎬 እንኳን ወደ TikTok ማውረጃ በደህና መጡ!\n\nቪዲዮ ለማውረድ የ TikTok ሊንክ ይላኩ።"
        btn_lang = "🌐 ቋንቋ ለመቀየር"
    elif lang == "om":
        text_msg = "🎬 Baga gara Buufata TikTok Nageenyaan Dhuftan!\n\nViidiyoo buufachuuf hidhaa TikTok ergaa."
        btn_lang = "🌐 Afaan Jijjiiruuf"
    else:
        text_msg = "🎬 Welcome to TikTok Downloader Bot!\n\nSend any TikTok link below to start."
        btn_lang = "🌐 Change Language"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(btn_lang, callback_data="/btn_lang"))
    bot.send_message(message.chat.id, text_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['/btn_lang', '/lang_en', '/lang_am', '/lang_om', '/btn_home'])
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
        markup.row(InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="/lang_om"))
        markup.row(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        bot.edit_message_text("🌐 Please select your language / ቋንቋ ይምረጡ / Afaan filadhaa:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    else:
        selected_lang = call.data.replace('/lang_', '')
        set_user_attr(u_id, "lang", selected_lang)
        
        if selected_lang == "am":
            confirm_text = "✅ ቋንቋዎ በተሳካ ሁኔታ ወደ አማርኛ ተቀይሯል።\n\nአሁን የ TikTok ሊንክዎን ይላኩ።"
        elif selected_lang == "om":
            confirm_text = "✅ Afaan keessan milkaa'inaan gara Afaan Oromotti jijjiirameera.\n\nAmma hidhaa TikTok keessan ergaa."
        else:
            confirm_text = "✅ Language successfully changed to English.\n\nNow send your TikTok link."

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        bot.edit_message_text(confirm_text, call.message.chat.id, call.message.message_id, reply_markup=markup)

# ----------------------------------------------------
# 2. TIKTOK LINK HANDLER (AD GATE WITH 3 BUTTONS)
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text and ('tiktok.com' in msg.text.lower() or 'vt.tiktok.com' in msg.text.lower()))
def handle_tiktok_link(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "tiktok_url", message.text.strip())
    
    expiry_time = get_user_attr(u_id, "ad_pass_expiry", 0)
    if current_time < expiry_time:
        send_quality_options(message.chat.id, get_user_attr(u_id, "lang", "en"))
        return

    lang = get_user_attr(u_id, "lang", "en")
    if lang == "am":
        gate_msg = "🔥 ለቀጣይ 24 ሰዓት በነፃ ለማውረድ ማስታወቂያውን ይዩ ወይም ፕሪሚየም ይግዙ:"
        b_ad = "👉 ማስታወቂያ ይመልከቱ (15s)"
        b_prem = "⭐ ፕሪሚየም ይግዙ"
        b_skip = "⏭️ ይዝለሉ (ወደ ድረ-ገጽ ይሂዱ)"
    elif lang == "om":
        gate_msg = "🔥 Viidiyoo bilisaan buufachuuf beeksisa ilaalaa ykn piriimiyamii bitaa:"
        b_ad = "👉 Beeksisa Daawwadhaa (15s)"
        b_prem = "⭐ Piriimiyamii Bitaa"
        b_skip = "⏭️ Irra darbi (Marsariitii)"
    else:
        gate_msg = "To continue, watch a short ad (15 sec), skip to web, or buy premium:"
        b_ad = "👉 Watch ad (15s)"
        b_prem = "⭐ Buy Premium"
        b_skip = "⏭️ Skip (Open Web)"

    markup = InlineKeyboardMarkup()
    # 1st Button: Watch Ad (Opens WebApp)
    markup.add(InlineKeyboardButton(b_ad, web_app=WebAppInfo(url=WEB_APP_URL), style="danger"))
    # 2nd Button: Buy Premium
    markup.add(InlineKeyboardButton(b_prem, callback_data="/buy_premium", style="primary"))
    # 3rd Button: Skip / Web Link Direct Access
    markup.add(InlineKeyboardButton(b_skip, url=WEB_APP_URL, style="success"))
    # Home button
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    bot.send_message(message.chat.id, gate_msg, reply_markup=markup)

# ----------------------------------------------------
# 3. WEB APP SIGNAL (AUTO-PASS 24 HOURS)
# ----------------------------------------------------
@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "ad_pass_expiry", current_time + 86400) # 24 Hours
    
    bot.send_message(message.chat.id, "✅ Ad verified successfully! 24-hour pass activated.")
    send_quality_options(message.chat.id, get_user_attr(u_id, "lang", "en"))

# ----------------------------------------------------
# 4. QUALITY OPTIONS MENU
# ----------------------------------------------------
def send_quality_options(chat_id, lang):
    if lang == "am":
        prompt_text = "🎥 የማውረድ አማራጭ ይምረጡ:"
        b_no_wm, b_wm, b_au = "🎬 ቪዲዮ (ያለ ዋተርማርክ)", "🏷️ ቪዲዮ (ከዋተርማርክ ጋር)", "🎵 ድምፅ ብቻ (MP3)"
    elif lang == "om":
        prompt_text = "🎥 Filannoo buufata filadhaa:"
        b_no_wm, b_wm, b_au = "🎬 Viidiyoo (Mallattoo Malee)", "🏷️ Viidiyoo (Mallattoo Wajjin)", "🎵 Sagalee Qofa (MP3)"
    else:
        prompt_text = "🎥 Choose download option:"
        b_no_wm, b_wm, b_au = "🎬 Video (No Watermark)", "🏷️ Video (With Watermark)", "🎵 Audio Only (MP3)"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(b_no_wm, callback_data="quality_nowatermark", style="success"))
    markup.add(InlineKeyboardButton(b_wm, callback_data="quality_watermark", style="primary"))
    markup.add(InlineKeyboardButton(b_au, callback_data="quality_audio", style="primary"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    bot.send_message(chat_id, prompt_text, reply_markup=markup)

# ----------------------------------------------------
# 5. PREMIUM SUBSCRIPTION DURATION MENU (1M, 3M, 6M, 1Y)
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == '/buy_premium')
def handle_premium_menu(call):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🗓️ 1 Month — 50 ⭐️", callback_data="buy_stars_50_30", style="primary"))
    markup.add(InlineKeyboardButton("🗓️ 3 Months — 120 ⭐️", callback_data="buy_stars_120_90", style="success"))
    markup.add(InlineKeyboardButton("🗓️ 6 Months — 220 ⭐️", callback_data="buy_stars_220_180", style="primary"))
    markup.add(InlineKeyboardButton("🗓️ 1 Year — 380 ⭐️", callback_data="buy_stars_380_365", style="success"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    msg = (
        "⭐ **TikTok Downloader Premium**\n\n"
        "Unlock unlimited ad-free downloads for your chosen duration:\n\n"
        "Choose your plan below 👇"
    )
    bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_stars_'))
def send_star_invoice(call):
    parts = call.data.split('_')
    stars = int(parts[2])
    days = int(parts[3])

    title = "TikTok Downloader Premium"
    description = f"Unlock unlimited ad-free access for {days} days."
    payload = f"premium_{days}_{call.from_user.id}"
    currency = "XTR"
    prices = [LabeledPrice(label=f"Premium ({days} Days)", amount=stars)]

    bot.send_invoice(
        call.message.chat.id,
        title=title,
        description=description,
        invoice_payload=payload,
        provider_token="",
        currency=currency,
        prices=prices,
        start_parameter="premium-sub"
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
        f"🎉 Payment Received!\n\nYour Premium Subscription is active for {days} days. Enjoy unlimited downloading!",
        parse_mode="Markdown"
    )

# ----------------------------------------------------
# 6. DOWNLOAD HANDLER
# ----------------------------------------------------
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

print("Bot running successfully...")
bot.infinity_polling()
