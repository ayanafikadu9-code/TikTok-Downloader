import os
import time
import threading
import requests
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from config import BOT_TOKEN, BOT_USERNAME, API_URL, WEBSITE_AD_URL, AD_WAIT_SECONDS

# NOTE on colored buttons: style="primary"/"success"/"danger" requires
# Telegram Bot API 9.4+ (Feb 2026). Make sure requirements.txt pulls a
# current pyTelegramBotAPI version (see requirements.txt) or the style
# keyword will be silently ignored and buttons show with no color.

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}


def get_user_attr(user_id, key, default=None):
    return user_data.get(user_id, {}).get(key, default)


def set_user_attr(user_id, key, value):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id][key] = value


# ----------------------------------------------------
# 1. COMMAND: /start  (also handles the ?start=verified deep link)
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_start(message):
    u_id = message.from_user.id
    lang = get_user_attr(u_id, "lang", "en")

    # Deep-link payload: t.me/<bot>?start=verified opens as "/start verified"
    parts = message.text.split(maxsplit=1)
    payload = parts[1] if len(parts) > 1 else None

    if payload == "verified":
        set_user_attr(u_id, "ad_pass_expiry", int(time.time()) + 86400)
        pending_url = get_user_attr(u_id, "tiktok_url")
        if pending_url:
            # They already had a link waiting — go straight to quality choice.
            send_quality_options(message.chat.id, lang)
            return
        # No pending link — fall through to the normal welcome message,
        # ad pass is already active for their next link.

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
    bot.send_message(message.chat.id, text_msg, reply_markup=markup, parse_mode="Markdown")


# ----------------------------------------------------
# 2. LANGUAGE SELECTION MENU
# ----------------------------------------------------
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
        bot.edit_message_text(
            "🌐 Please select your language / ቋንቋ ይምረጡ / Afaan filadhaa:",
            call.message.chat.id, call.message.message_id,
            reply_markup=markup, parse_mode="Markdown"
        )
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
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="primary"))
        bot.edit_message_text(confirm_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")


# ----------------------------------------------------
# 3. LINK DETECTION (AD GATE)
# ----------------------------------------------------
@bot.message_handler(func=lambda msg: msg.text and ('tiktok.com' in msg.text.lower() or 'vt.tiktok.com' in msg.text.lower()))
def handle_tiktok_link(message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "tiktok_url", message.text.strip())

    lang = get_user_attr(u_id, "lang", "en")
    expiry_time = get_user_attr(u_id, "ad_pass_expiry", 0)
    has_active_pass = current_time < expiry_time

    if not has_active_pass:
        send_ad_gate(message.chat.id, u_id, lang)
    else:
        send_quality_options(message.chat.id, lang)


def send_ad_gate(chat_id, u_id, lang, edit_message_id=None):
    # This same-origin timestamp powers the manual fallback button below,
    # in case the deep-link redirect doesn't fire on the user's device.
    set_user_attr(u_id, "ad_click_time", int(time.time()))

    if lang == "am":
        gate_msg = "🔥 ለቀጣይ 24 ሰዓት 10,000 ቪዲዮዎችን በነፃ ያውርዱ!\n\nማስታወቂያውን ይክፈቱ እና እስኪያልቅ ይጠብቁ — ራሱ በራሱ ይመለሳል።"
        b_ad = "👁️ ማስታወቂያውን ይክፈቱ"
        b_fallback = "✅ ተመልሻለሁ ግን አልተፈታም"
        b_prem = "⭐ ፕሪሚየም ይግዙ"
    elif lang == "om":
        gate_msg = "🔥 Sa'atii 24 ffaaf viidiyoo 10,000 bilisaan buufadhaa!\n\nBeeksisa banaa; xumurus ofumaan deebi'a."
        b_ad = "👁️ Beeksisa Banaa"
        b_fallback = "✅ Deebi'eera garuu hin hiikamne"
        b_prem = "⭐ Piriimiyamii Bitaa"
    else:
        gate_msg = "🔥 Open the ad below. When it finishes and you tap Continue, you'll be sent straight back here unlocked."
        b_ad = "👁️ Open Ad"
        b_fallback = "✅ I'm back but it's still locked"
        b_prem = "⭐ Buy Premium"

    markup = InlineKeyboardMarkup()
    # Real external link — opens the user's real browser so the ad network counts a real view.
    markup.add(InlineKeyboardButton(b_ad, url=WEBSITE_AD_URL, style="danger"))
    # Fallback only — normally unlocking happens automatically via the /start?verified deep link.
    markup.add(InlineKeyboardButton(b_fallback, callback_data="/verify_ad", style="success"))
    markup.add(InlineKeyboardButton(b_prem, callback_data="/buy_premium", style="primary"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    if edit_message_id:
        bot.edit_message_text(gate_msg, chat_id, edit_message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, gate_msg, reply_markup=markup, parse_mode="Markdown")


# ----------------------------------------------------
# 3b. FALLBACK MANUAL VERIFY (only needed if the deep link didn't fire)
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == '/verify_ad')
def handle_verify_ad_fallback(call):
    u_id = call.from_user.id
    lang = get_user_attr(u_id, "lang", "en")

    click_time = get_user_attr(u_id, "ad_click_time")
    current_time = int(time.time())

    if click_time is None or (current_time - click_time) < AD_WAIT_SECONDS:
        remaining = AD_WAIT_SECONDS - (current_time - click_time) if click_time else AD_WAIT_SECONDS
        if lang == "am":
            alert_txt = f"⚠️ እባክዎ መጀመሪያ ማስታወቂያውን ይክፈቱ እና ቢያንስ {max(remaining, 1)} ሰከንድ ይቆዩ።"
        elif lang == "om":
            alert_txt = f"⚠️ Maaloo dura beeksisa banaa, sekondii {max(remaining, 1)} eegi."
        else:
            alert_txt = f"⚠️ Please open the ad first and wait at least {max(remaining, 1)} more second(s)."
        bot.answer_callback_query(call.id, alert_txt, show_alert=True)
        return

    set_user_attr(u_id, "ad_pass_expiry", current_time + 86400)
    bot.answer_callback_query(call.id, "✅ Verified!")
    send_quality_options(call.message.chat.id, lang, edit_message_id=call.message.message_id)


def send_quality_options(chat_id, lang, edit_message_id=None):
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

    if edit_message_id:
        bot.edit_message_text(prompt_text, chat_id, edit_message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, prompt_text, reply_markup=markup, parse_mode="Markdown")


# ----------------------------------------------------
# 5. TELEGRAM STARS PREMIUM MENU & INVOICING
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == '/buy_premium')
def handle_premium_menu(call):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🥉 1 month — 50 ⭐️ (30% OFF)", callback_data="buy_stars_50", style="primary"))
    markup.add(InlineKeyboardButton("🔥 3 months — 105 ⭐️ (30% OFF)", callback_data="buy_stars_105", style="success"))
    markup.add(InlineKeyboardButton("💎 12 months — 350 ⭐️ (30% OFF)", callback_data="buy_stars_350", style="primary"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

    msg = (
        "🚫 Remove ads\n\n"
        "Download videos without mandatory ads or waiting.\n\n"
        "Premium includes:\n"
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
        f"🎉 Payment Received!\n\nYour Premium Subscription is now active for {days} days. Enjoy ad-free downloading!",
        parse_mode="Markdown"
    )


# ----------------------------------------------------
# 6. EXECUTE DOWNLOAD
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_download(call):
    u_id = call.from_user.id
    quality = call.data.replace('quality_', '')
    url = get_user_attr(u_id, "tiktok_url")

    if not url:
        bot.edit_message_text("❌ Session expired. Please send the TikTok link again.", call.message.chat.id, call.message.message_id)
        return

    bot.edit_message_text("⏳ Processing your request...", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

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
                markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="/btn_home", style="danger"))

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

                bot.edit_message_text("✅ Download Complete!", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.edit_message_text("❌ Could not extract download link.", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text("❌ API Error. Please try a different TikTok link.", call.message.chat.id, call.message.message_id)
    except Exception:
        bot.edit_message_text("❌ Connection error while downloading. Try again.", call.message.chat.id, call.message.message_id)


# ----------------------------------------------------
# 7. KEEP-ALIVE WEB SERVER (so Render treats this as a real Web Service
#    and an uptime pinger has something to hit — see hosting notes)
# ----------------------------------------------------
app = Flask(__name__)


@app.route('/')
def health():
    return "Bot is alive!", 200


def run_bot():
    print("Bot polling starting...")
    bot.infinity_polling()


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
