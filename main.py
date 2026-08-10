import time
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

def get_user_attr(user_id, key, default=None):
    return user_data.get(user_id, {}).get(key, default)

def set_user_attr(user_id, key, value):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id][key] = value

# ----------------------------------------------------
# 1. /START & LANGUAGE SELECTION (FULLY COLORED)
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
    markup.add(InlineKeyboardButton(btn_lang, callback_data="/btn_lang", style="primary"))
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
            InlineKeyboardButton("🇬🇧 English", callback_data="/lang_en", style="primary"),
            InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="/lang_am", style="success")
        )
        markup.row(InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="/lang_om", style="primary"))
        markup.row(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))
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
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))
        bot.edit_message_text(confirm_text, call.message.chat.id, call.message.message_id, reply_markup=markup)

# ----------------------------------------------------
# 2. TIKTOK LINK HANDLER (AD GATE WITH FULL COLORS)
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
        gate_msg = "🔥 ቪዲዮ ለማውረድ የ 15 ሰከንድ ማስታወቂያ ይመልከቱ ወይም ድረ-ገጹን ይጎብኙ:"
        b_ad = "👉 ማስታወቂያ ይመልከቱ (15s)"
        b_skip = "⏭️ ድረ-ገጽ ክፈት (Skip)"
        b_prem = "⭐ ፕሪሚየም ይግዙ"
    elif lang == "om":
        gate_msg = "🔥 Viidiyoo buufachuuf beeksisa sekondii 15 ilaalaa ykn marsariitii bitaa:"
        b_ad = "👉 Beeksisa Ilaalaa (15s)"
        b_skip = "⏭️ Marsariitii Banuu (Skip)"
        b_prem = "⭐ Piriimiyamii Bitaa"
    else:
        gate_msg = "To continue, watch a short ad (15 sec), skip to web, or buy premium:"
        b_ad = "👉 Watch ad (15s)"
        b_skip = "⏭️ Skip (Open Web)"
        b_prem = "⭐ Buy Premium"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(b_ad, callback_data="start_countdown", style="danger"))
    markup.add(InlineKeyboardButton(b_prem, callback_data="/buy_premium", style="primary"))
    markup.add(InlineKeyboardButton(b_skip, url=WEB_APP_URL, style="success"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    bot.send_message(message.chat.id, gate_msg, reply_markup=markup)

# ----------------------------------------------------
# 3. LIVE 15-SECOND COUNTDOWN & RE-SEND PROMPT
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == 'start_countdown')
def handle_ad_countdown(call):
    u_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    for remaining in range(14, 0, -1):
        try:
            bot.edit_message_text(
                f"⏳ **Please watch the ad...**\n\nUnlocking in: **{remaining} seconds**",
                chat_id,
                msg_id,
                parse_mode="Markdown"
            )
            time.sleep(1)
        except Exception:
            pass

    current_time = int(time.time())
    set_user_attr(u_id, "ad_pass_expiry", current_time + 86400)

    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        pass

    bot.send_message(
        chat_id, 
        "✅ **Ad completed successfully!** 24-hour pass activated.\n\n📌 **Please send your TikTok link again to download your video!**",
        parse_mode="Markdown"
    )

# ----------------------------------------------------
# 4. QUALITY OPTIONS MENU (FULLY COLORED)
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
# 5. PREMIUM SUBSCRIPTION MENU (FULLY COLORED)
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
