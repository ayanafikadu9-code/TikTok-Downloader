
import time
import sqlite3
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice

# ============ CONFIGURATION ============
BOT_TOKEN = "8913902406:AAE5YB6XyXY4JBXbODODwOTl4P-dnV7T2rA"
API_URL = "https://silent-mud-7026.codeofsaladin.workers.dev/tiktok"
WEB_APP_URL = "https://ayanafikadu9-code.github.io/TikTok-Downloader/"
DB_FILE = "bot_data.db"
ADMIN_ID = 123456789  # ⚠️ Replace with your actual Telegram User ID

bot = telebot.TeleBot(BOT_TOKEN)

# ----------------------------------------------------
# DATABASE INITIALIZATION & HELPERS
# ----------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'en',
            ad_pass_expiry INTEGER DEFAULT 0,
            tiktok_url TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT lang, ad_pass_expiry, tiktok_url FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"lang": row[0], "ad_pass_expiry": row[1], "tiktok_url": row[2]}
    return {"lang": "en", "ad_pass_expiry": 0, "tiktok_url": ""}

def set_user_attr(user_id, key, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
    conn.commit()
    conn.close()

def get_all_user_ids():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

init_db()

# ----------------------------------------------------
# ADMIN COMMANDS (STATS & BROADCAST)
# ----------------------------------------------------
@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = get_all_user_ids()
    bot.reply_to(message, f"📊 **Bot Database Stats:**\n\nTotal Registered Users: **{len(users)}**", parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def admin_broadcast(message):
    if message.from_user.id != ADMIN_ID:
        return

    # Extract message after /broadcast
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.reply_to(message, "⚠️ **Usage:** `/broadcast Your message here`", parse_mode="Markdown")
        return

    broadcast_msg = command_parts[1]
    all_users = get_all_user_ids()
    
    if not all_users:
        bot.reply_to(message, "❌ No users found in the database.")
        return

    status_msg = bot.reply_to(message, f"🚀 **Starting Broadcast to {len(all_users)} users...**", parse_mode="Markdown")
    
    success_count = 0
    fail_count = 0

    for user_id in all_users:
        try:
            bot.send_message(user_id, broadcast_msg, parse_mode="Markdown")
            success_count += 1
            time.sleep(0.05)  # Prevent hitting API rate limits
        except Exception:
            fail_count += 1

    report = (
        f"📢 **Broadcast Completed!**\n\n"
        f"✅ Successfully Delivered: **{success_count}**\n"
        f"❌ Failed (Blocked/Deleted): **{fail_count}**\n"
        f"👥 Total Targeted: **{len(all_users)}**"
    )
    bot.edit_message_text(report, status_msg.chat.id, status_msg.message_id, parse_mode="Markdown")

# ----------------------------------------------------
# 1. COMMAND: /start
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_start(message):
    u_id = message.from_user.id
    u_data = get_user_data(u_id)
    lang = u_data["lang"]

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
# 3. LINK DETECTION (AD GATE & ACCESS CHECK)
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: 'tiktok.com' in msg.text.lower() or 'vt.tiktok.com' in msg.text.lower())
def handle_tiktok_link(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "tiktok_url", message.text.strip())
    
    u_data = get_user_data(u_id)
    lang = u_data["lang"]
    expiry_time = u_data["ad_pass_expiry"]
    has_active_pass = current_time < expiry_time

    if not has_active_pass:
        if lang == "am":
            gate_msg = "🔥 **ቪዲዮ ለማውረድ ማስታወቂያ ይመልከቱ ወይም ፕሪሚየም ይግዙ:**"
            b_ad, b_prem = "👁️ ማስታወቂያ ይመልከቱ (15s)", "⭐ ፕሪሚየም ይግዙ (Telegram Stars)"
        elif lang == "om":
            gate_msg = "🔥 **Viidiyoo buufachuuf beeksisa daawwadhaa ykn piriimiyamii bitaa:**"
            b_ad, b_prem = "👁️ Beeksisa Daawwadhaa (15s)", "⭐ Piriimiyamii Bitaa (Telegram Stars)"
        else:
            gate_msg = "🔥 **To continue, watch a short ad or buy Premium:**"
            b_ad, b_prem = "👉 Watch ad (15s)", "⭐ Buy Premium"

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
        
        u_data = get_user_data(u_id)
        lang = u_data["lang"]
        bot.send_message(message.chat.id, "✅ **Ad verified! 24-Hour Pass Unlocked.**")
        send_quality_options(message.chat.id, lang)

# ----------------------------------------------------
# 5. TELEGRAM STARS PREMIUM MENU & INVOICING
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data in ['/buy_premium', '/btn_home'])
def handle_premium_menu(call):
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
# 6. EXECUTE DOWNLOAD
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_download(call):
    u_id = call.from_user.id
    quality = call.data.replace('quality_', '')
    u_data = get_user_data(u_id)
    url = u_data["tiktok_url"]

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

print("Bot running with SQLite Broadcast & Stats feature...")
bot.infinity_polling()
