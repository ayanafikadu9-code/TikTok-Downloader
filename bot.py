#!/usr/bin/env python3
"""
TikTok Downloader Telegram Bot - FIXED
Features:
- /start -> VERTICAL language selection (English, Amharic, Afaan Oromoo)
- After language chosen -> ask user to send TikTok link
- When TikTok link received -> show VERTICAL ad gate with Premium option
- After verify -> show VERTICAL quality menu
- Payment: Buy Premium (5 Telegram Stars) for 30-day pass
"""

import os
import re
import time
import json
import sqlite3
import secrets
import threading
import subprocess
import traceback
from datetime import datetime, timedelta
from typing import Optional

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN environment variable required.")

HOST = os.getenv("HOST", "")
AD_PAGE = os.getenv("AD_PAGE", "https://ayanafikadu9-code.github.io/TikTok-Downloader/")
PREMIUM_URL = os.getenv("PREMIUM_URL", AD_PAGE)

TIKWM_API_URL = os.getenv("TIKWM_API_URL", "").strip()
TIKWM_API_KEY = os.getenv("TIKWM_API_KEY", "").strip()

KEEPALIVE_ENABLED = os.getenv("KEEPALIVE_ENABLED", "0") == "1"
KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", 300))

DB_FILE = os.getenv("DB_FILE", "bot_data.db")
_db_lock = threading.Lock()

TIKTOK_RE = re.compile(r"(https?://)?(www\.)?(vm\.)?tiktok\.com/|tiktok\.com/")

flask_app = Flask(__name__)
CORS(flask_app, resources={r"/*": {"origins": "*"}})

# ============ DATABASE ============
def init_db():
    with _db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'en',
                last_tiktok_url TEXT,
                pass_expires_at INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                user_id INTEGER,
                tiktok_url TEXT,
                status TEXT,
                created_at INTEGER
            )
        """)
        conn.commit()
        conn.close()

def _db_exec(query, params=(), fetchone=False, fetchall=False):
    with _db_lock:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute(query, params)
        result = c.fetchone() if fetchone else (c.fetchall() if fetchall else None)
        conn.commit()
        conn.close()
        return result

def set_user_language(user_id: int, lang: str):
    _db_exec(
        "INSERT INTO users (user_id, language) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
        (user_id, lang)
    )

def get_user(user_id: int) -> dict:
    row = _db_exec(
        "SELECT user_id, language, last_tiktok_url, pass_expires_at FROM users WHERE user_id=?",
        (user_id,),
        fetchone=True
    )
    if not row:
        _db_exec("INSERT OR IGNORE INTO users (user_id, language) VALUES (?, ?)", (user_id, "en"))
        return {"user_id": user_id, "language": "en", "last_tiktok_url": None, "pass_expires_at": None}
    return {
        "user_id": row[0],
        "language": row[1] or "en",
        "last_tiktok_url": row[2],
        "pass_expires_at": row[3]
    }

def set_user_tiktok_url(user_id: int, url: str):
    _db_exec("UPDATE users SET last_tiktok_url=? WHERE user_id=?", (url, user_id))

def set_user_pass(user_id: int, expires_at_ts: int):
    _db_exec("UPDATE users SET pass_expires_at=? WHERE user_id=?", (expires_at_ts, user_id))

def user_has_valid_pass(user_id: int) -> bool:
    u = get_user(user_id)
    if not u or not u.get("pass_expires_at"):
        return False
    return int(time.time()) < int(u["pass_expires_at"])

def create_job(user_id: int, tiktok_url: str) -> str:
    job_id = secrets.token_hex(12)
    _db_exec(
        "INSERT INTO jobs (job_id, user_id, tiktok_url, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, user_id, tiktok_url, "pending", int(time.time()))
    )
    return job_id

def update_job_status(job_id: str, status: str):
    _db_exec("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))

# ============ TELEGRAM API (ASYNC-FRIENDLY) ============
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup.to_json()
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def answer_callback_query(callback_query_id: str, text: Optional[str] = None, alert: bool = False):
    url = f"{TELEGRAM_API_BASE}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    payload["show_alert"] = alert
    requests.post(url, json=payload, timeout=15)

def send_file_via_bot(chat_id: int, file_path: str, file_type: str = "video", caption: Optional[str] = None):
    method = "sendVideo" if file_type == "video" else "sendAudio"
    url = f"{TELEGRAM_API_BASE}/{method}"
    with open(file_path, "rb") as fh:
        files = {file_type: fh}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        r = requests.post(url, data=data, files=files, timeout=180)
        r.raise_for_status()
        return r.json()

# ============ LANGUAGE STRINGS ============
LANG_STRINGS = {
    "en": {
        "welcome": "🌐 <b>Choose your language:</b>",
        "lang_set": "✅ Language set to <b>English</b>\n\nNow please send your TikTok link.",
        "send_link": "❌ Please send a valid TikTok link.",
        "link_received": "✅ TikTok link saved!\n\nNow open the ad page, watch the ad, and press 'Verify'.",
        "verified": "✅ Verification accepted!\n\nChoose the download format:",
        "no_pass": "❌ You need a valid pass. Open the ad page and press Verify.",
        "no_link": "❌ No TikTok link found. Send your link first.",
        "processing": "⏳ Processing your request...",
        "premium_ok": "✅ Premium activated for 30 days!",
    },
    "am": {
        "welcome": "🌐 <b>ቋንቋዎን ይምረጡ:</b>",
        "lang_set": "✅ ቋንቋ ወደ <b>አማርኛ</b> ተቀይሯል\n\nአሁን የTikTok ሊንክ ይላኩ።",
        "send_link": "❌ እባክዎ ትክክለኛ TikTok ሊንክ ይላኩ።",
        "link_received": "✅ TikTok ሊንክ ተወስጇል!\n\nሁን ad ገጽ ይክፈቱ፣ ይመልከቱ፣ 'Verify' ይጫኑ።",
        "verified": "✅ ማረጋገጫ ተቀበለ!\n\nየእንቅስቃሴ ቅርጸት ይምረጡ:",
        "no_pass": "❌ ትክክለኛ ፓስ ያስፈልግዎታል።",
        "no_link": "❌ TikTok ሊንክ አልተገኘም።",
        "processing": "⏳ ጥያቄዎ ተሠራ ይቆይ...",
        "premium_ok": "✅ ፕሪሚየም 30 ቀናት ነቅተዋል!",
    },
    "om": {
        "welcome": "🌐 <b>Afaan filadhu:</b>",
        "lang_set": "✅ Afaan <b>Afaan Oromoo</b> irra jijjiirame\n\nHar'a linki TikTok ergaa.",
        "send_link": "❌ Maaloo linki TikTok sirrii ergaa.",
        "link_received": "✅ Linki TikTok qabsiisuun guutame!\n\nFaqaasaa ilaalcha banaa fi Verify tuqaa buusa.",
        "verified": "✅ Mirkaneessisen fudhate!\n\nAkaamsaa downloodiif filadu:",
        "no_pass": "❌ Pass sirrii barbaaddu.",
        "no_link": "❌ Linki TikTok hin argamne.",
        "processing": "⏳ Gaaffii kee hojii itti fufuu...",
        "premium_ok": "✅ Preemiyam guyyoota 30 hewaa!",
    },
}

LANG_BUTTONS = {"en": "🇬🇧 English", "am": "🇪🇹 Amharic (አማርኛ)", "om": "🌍 Afaan Oromoo"}

# ============ KEYBOARDS (VERTICAL LAYOUT) ============
def make_language_keyboard():
    """VERTICAL language selection - each button on separate line"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇹 Amharic (አማርኛ)", callback_data="lang_am")],
        [InlineKeyboardButton("🌍 Afaan Oromoo", callback_data="lang_om")],
    ])

def make_ad_gate_keyboard():
    """VERTICAL ad gate buttons"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Open Ad Page", url=AD_PAGE)],
        [InlineKeyboardButton("✅ Verify / I Watched", callback_data="verify_ad")],
        [InlineKeyboardButton("⭐ Buy Premium (5 ⭐)", callback_data="buy_stars")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def make_quality_keyboard():
    """VERTICAL quality selection - each button on separate line"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Video (No Watermark)", callback_data="quality_no_watermark")],
        [InlineKeyboardButton("🏷️ Video (With Watermark)", callback_data="quality_watermark")],
        [InlineKeyboardButton("🎵 Audio Only (MP3)", callback_data="quality_audio")],
        [InlineKeyboardButton("◀️ Back", callback_data="cancel")],
    ])

# ============ DOWNLOAD HANDLING ============
def call_tikwm_api(tiktok_url: str, mode: str) -> Optional[str]:
    if not TIKWM_API_URL:
        return None
    try:
        params = {"url": tiktok_url, "type": mode}
        headers = {"Authorization": f"Bearer {TIKWM_API_KEY}"} if TIKWM_API_KEY else {}
        resp = requests.get(TIKWM_API_URL, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            for k in ("download_url", "url", "data", "download"):
                if k in data and isinstance(data[k], str) and data[k].startswith("http"):
                    return data[k]
        return None
    except Exception:
        return None

def download_via_yt_dlp(tiktok_url: str, out_path: str, extract_audio: bool = False):
    if extract_audio:
        cmd = ["yt-dlp", "-x", "--audio-format", "mp3", "-o", out_path, tiktok_url]
    else:
        cmd = ["yt-dlp", "-o", out_path, "-f", "best[ext=mp4]", tiktok_url]
    subprocess.check_call(cmd, timeout=600)

def process_download_job(chat_id: int, user_id: int, tiktok_url: str, mode: str):
    job_id = create_job(user_id, tiktok_url)
    update_job_status(job_id, "started")
    try:
        dl_url = call_tikwm_api(tiktok_url, mode) if TIKWM_API_URL else None
        tmp_filename = None
        
        if dl_url:
            # Download via API
            ext = "mp3" if mode == "audio" else "mp4"
            tmp_filename = f"/tmp/{job_id}.{ext}"
            with requests.get(dl_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp_filename, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
            send_file_via_bot(chat_id, tmp_filename, file_type="audio" if mode == "audio" else "video", caption="✅ Here is your file")
            update_job_status(job_id, "sent")
        else:
            # Download via yt-dlp
            if mode == "audio":
                out_path = f"/tmp/{job_id}.%(ext)s"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=True)
                found = f"/tmp/{job_id}.mp3"
                if os.path.exists(found):
                    send_file_via_bot(chat_id, found, file_type="audio", caption="✅ Here is your audio (MP3)")
                    tmp_filename = found
                update_job_status(job_id, "sent")
            else:
                out_path = f"/tmp/{job_id}.mp4"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=False)
                if os.path.exists(out_path):
                    send_file_via_bot(chat_id, out_path, file_type="video", caption="✅ Here is your video")
                    tmp_filename = out_path
                update_job_status(job_id, "sent")
        
        if tmp_filename and os.path.exists(tmp_filename):
            os.remove(tmp_filename)
    except Exception as e:
        update_job_status(job_id, "failed")
        try:
            send_telegram_message(chat_id, f"❌ Error: {str(e)[:100]}")
        except Exception:
            pass

# ============ BOT HANDLERS ============
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    send_telegram_message(
        chat_id,
        "Welcome! / ደህና መጡ! / Akam!\n\n🌐 <b>Choose your language:</b>",
        reply_markup=make_language_keyboard()
    )

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    data = query.data or ""
    user_id = query.from_user.id
    chat_id = query.message.chat.id if query.message else user_id
    
    # Get user language
    user = get_user(user_id)
    lang = user.get("language", "en")
    if lang not in LANG_STRINGS:
        lang = "en"
    strings = LANG_STRINGS[lang]

    # Handle language selection
    if data.startswith("lang_"):
        lang_code = data.split("_", 1)[1]
        if lang_code not in LANG_BUTTONS:
            lang_code = "en"
        set_user_language(user_id, lang_code)
        
        strings = LANG_STRINGS.get(lang_code, LANG_STRINGS["en"])
        answer_callback_query(query.id, f"✅ {LANG_BUTTONS.get(lang_code)}")
        send_telegram_message(chat_id, strings["lang_set"])
        return

    # Handle cancel
    if data == "cancel":
        answer_callback_query(query.id, "Cancelled.")
        try:
            query.edit_message_text("❌ Operation cancelled.")
        except Exception:
            pass
        return

    # Handle ad verification
    if data == "verify_ad":
        expires_at = int((datetime.utcnow() + timedelta(hours=24)).timestamp())
        set_user_pass(user_id, expires_at)
        answer_callback_query(query.id, "✅ Verified!")
        send_telegram_message(chat_id, strings["verified"], reply_markup=make_quality_keyboard())
        return

    # Handle buy premium (stars)
    if data == "buy_stars":
        answer_callback_query(query.id, "Opening payment...")
        await context.bot.send_invoice(
            chat_id=chat_id,
            title="Premium Pass - 30 Days",
            description="Unlock instant video downloads without watching ads for 30 days.",
            payload="premium_pass_30days",
            provider_token="",  # Must be empty for Telegram Stars
            currency="XTR",  # Telegram Stars currency code
            prices=[LabeledPrice("Premium Pass", 500)]  # 5 Telegram Stars = 500 (in cents)
        )
        return

    # Handle quality selection
    if data.startswith("quality_"):
        if not user_has_valid_pass(user_id):
            answer_callback_query(query.id, strings["no_pass"], alert=True)
            return
        
        choice = data.split("_", 1)[1]
        user = get_user(user_id)
        tiktok_url = user.get("last_tiktok_url")
        if not tiktok_url:
            answer_callback_query(query.id, strings["no_link"], alert=True)
            return
        
        answer_callback_query(query.id, strings["processing"])
        threading.Thread(target=process_download_job, args=(chat_id, user_id, tiktok_url, choice), daemon=True).start()
        return

    answer_callback_query(query.id, "")

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pre-checkout for Telegram Stars payment"""
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle successful payment - grant 30-day premium pass"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    user = get_user(user_id)
    lang = user.get("language", "en")
    if lang not in LANG_STRINGS:
        lang = "en"
    strings = LANG_STRINGS[lang]
    
    # Grant 30-day access
    expires_at = int((datetime.utcnow() + timedelta(days=30)).timestamp())
    set_user_pass(user_id, expires_at)
    
    send_telegram_message(
        chat_id,
        strings["premium_ok"] + "\n\n" + strings["verified"],
        reply_markup=make_quality_keyboard()
    )

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    user = get_user(user_id)
    lang = user.get("language", "en")
    if lang not in LANG_STRINGS:
        lang = "en"
    strings = LANG_STRINGS[lang]

    if TIKTOK_RE.search(text):
        set_user_tiktok_url(user_id, text)
        send_telegram_message(
            chat_id,
            strings["link_received"],
            reply_markup=make_ad_gate_keyboard()
        )
        return

    send_telegram_message(chat_id, strings["send_link"])

# ============ FLASK ============
@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": int(time.time())})

def run_flask():
    port = int(os.getenv("PORT", "5000"))
    flask_app.run(host="0.0.0.0", port=port, threaded=True)

def keepalive_loop():
    if not KEEPALIVE_ENABLED or not HOST:
        return
    target = HOST.rstrip("/") + "/health"
    while True:
        try:
            requests.get(target, timeout=10)
        except Exception:
            pass
        time.sleep(KEEPALIVE_INTERVAL)

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    if KEEPALIVE_ENABLED:
        threading.Thread(target=keepalive_loop, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    print("🤖 Bot started!")
    application.run_polling()

if __name__ == "__main__":
    main()
