import time
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ CONFIGURATION ============
BOT_TOKEN = "8913902406:AAE5YB6XyXY4JBXbODODwOTl4P-dnV7T2rA"  

API_URL = "https://silent-mud-7026.codeofsaladin.workers.dev/tiktok"
AD_LINK = "https://your-ad-link-here.com"        
PREMIUM_LINK = "https://t.me/ayanafekadu"   
REQUIRED_WAIT = 10  # 10-second timer

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
    # Blue Primary Button
    markup.add(InlineKeyboardButton(btn_lang, callback_data="/btn_lang", style="primary"))
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
            InlineKeyboardButton("🇬🇧 English", callback_data="/lang_en", style="primary"),
            InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="/lang_am", style="primary")
        )
        markup.row(InlineKeyboardButton("🇪🇹 Afaan Oromoo", callback_data="/lang_om", style="primary"))
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
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="primary"))

        bot.edit_message_text(confirm_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# 3. LINK DETECTION (AD GATE & QUALITY SELECTOR)
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
        set_user_attr(u_id, "ad_click_time", current_time)
        if lang == "am":
            gate_msg = "🔥 **ለቀጣዩ 24 ሰዓት 10,000 ቪዲዮዎችን በነፃ ያውርዱ!**\n\n1️⃣ **ማስታወቂያ ይመልከቱ (10 ሰከንድ)** – የ 10,000 ቪዲዮ ማውረጃ ፈቃድዎን አሁኑኑ ይክፈቱ!\n2️⃣ **ፕሪሚየም ይግዙ** – ያለ ምንም ማስታወቂያ የሜጋ ፈቃድ ያግኙ።"
            b_ad, b_claim, b_prem = "👁️ ማስታወቂያ ይመልከቱ (10s)", "✅ ማስታወቂያ ተመልክቻለሁ", "⭐ ፕሪሚየም ይግዙ"
        elif lang == "om":
            gate_msg = "🔥 **Sa'aatii 24 dhufuuf viidiyooyyii 10,000 bilisaan buufadhaa!**\n\n1️⃣ **Beeksisa Daawwadhaa (10s)** – Eeyyama viidiyoo 10,000 amma banaa!\n2️⃣ **Piriimiyamiin Bitaa** – Beeksisa malee fayyadamaa."
            b_ad, b_claim, b_prem = "👁️ Beeksisa Daawwadhaa (10s)", "✅ Beeksisaan Daawwadhada", "⭐ Piriimiyamii Bitaa"
        else:
            gate_msg = "🔥 **Unlock 10,000 FREE Video Downloads for 24 Hours!**\n\n1️⃣ **Watch 10s Ad** – Unlock your pass instantly!\n2️⃣ **Buy Premium** – Get unlimited downloads."
            b_ad, b_claim, b_prem = "👁️ Watch Ad (10s)", "✅ I Watched the Ad", "⭐ Buy Premium"

        markup = InlineKeyboardMarkup()
        # Red Danger style for watching ad
        markup.add(InlineKeyboardButton(b_ad, url=AD_LINK, style="danger"))
        # Green Success style for verifying ad
        markup.add(InlineKeyboardButton(b_claim, callback_data="/verify_ad", style="success"))
        # Blue Primary style for premium link
        markup.add(InlineKeyboardButton(b_prem, url=PREMIUM_LINK, style="primary"))
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        
        bot.send_message(message.chat.id, gate_msg, reply_markup=markup, parse_mode="Markdown")
    else:
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
        # Green button for No Watermark Video
        markup.add(InlineKeyboardButton(b_no_wm, callback_data="quality_nowatermark", style="success"))
        # Blue button for Watermarked Video
        markup.add(InlineKeyboardButton(b_wm, callback_data="quality_watermark", style="primary"))
        # Danger/Red button for Audio
        markup.add(InlineKeyboardButton(b_au, callback_data="quality_audio", style="danger"))
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home"))
        
        bot.send_message(message.chat.id, prompt_text, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# 4. TIMER VERIFICATION & MAIN MENU CALLBACKS
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data in ['/verify_ad', '/btn_home'])
def handle_general_callbacks(call):
    u_id = call.from_user.id
    current_time = int(time.time())

    if call.data == '/btn_home':
        send_start(call.message)
        return

    click_time = get_user_attr(u_id, "ad_click_time", 0)
    time_passed = current_time - click_time

    if time_passed < REQUIRED_WAIT:
        time_left = REQUIRED_WAIT - time_passed
        bot.answer_callback_query(call.id, f"Wait {time_left} more seconds!", show_alert=True)
    else:
        set_user_attr(u_id, "ad_pass_expiry", current_time + 86400)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="primary"))
        bot.edit_message_text("🎉 **Success! Unlocked for 24 hours.** Send your TikTok link again!", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# 5. EXECUTE DOWNLOAD (DIRECT TELEGRAM STREAMING)
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
                markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="primary"))

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
