#!/usr/bin/env python3
"""
TikTok Downloader Telegram Bot - ENHANCED
Features:
- VERTICAL language selection with COLORED buttons
- Strict ad verification - MUST watch 15 seconds
- Connected to ad page with job tracking
- Automatic video download after verification
- Premium pass: 100 Telegram Stars = LIFETIME access
"""

import os
import re
import time
import json
import sqlite3
import secrets
import threading
import subprocess
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

HOST = os.getenv("HOST", "https://your-render-url.onrender.com")
AD_PAGE_URL = os.getenv("AD_PAGE_URL", "https://ayanafikadu9-code.github.io/TikTok-Downloader/")
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
                is_premium BOOLEAN DEFAULT 0,
                premium_expires_at INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ad_jobs (
                job_id TEXT PRIMARY KEY,
                user_id INTEGER,
                chat_id INTEGER,
                tiktok_url TEXT,
                status TEXT,
                verified BOOLEAN DEFAULT 0,
                created_at INTEGER,
                verified_at INTEGER
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
        "SELECT user_id, language, last_tiktok_url, is_premium, premium_expires_at FROM users WHERE user_id=?",
        (user_id,),
        fetchone=True
    )
    if not row:
        _db_exec("INSERT OR IGNORE INTO users (user_id, language) VALUES (?, ?)", (user_id, "en"))
        return {"user_id": user_id, "language": "en", "last_tiktok_url": None, "is_premium": False, "premium_expires_at": None}
    return {
        "user_id": row[0],
        "language": row[1] or "en",
        "last_tiktok_url": row[2],
        "is_premium": bool(row[3]),
        "premium_expires_at": row[4]
    }

def set_user_tiktok_url(user_id: int, url: str):
    _db_exec("UPDATE users SET last_tiktok_url=? WHERE user_id=?", (url, user_id))

def set_user_premium(user_id: int):
    """Grant LIFETIME premium (no expiry)"""
    _db_exec("UPDATE users SET is_premium=1, premium_expires_at=NULL WHERE user_id=?", (user_id,))

def user_has_premium(user_id: int) -> bool:
    u = get_user(user_id)
    return u.get("is_premium", False)

def create_ad_job(user_id: int, chat_id: int, tiktok_url: str) -> str:
    job_id = secrets.token_hex(16)
    _db_exec(
        "INSERT INTO ad_jobs (job_id, user_id, chat_id, tiktok_url, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, user_id, chat_id, tiktok_url, "pending", int(time.time()))
    )
    return job_id

def get_ad_job(job_id: str) -> dict:
    row = _db_exec(
        "SELECT job_id, user_id, chat_id, tiktok_url, status, verified, created_at FROM ad_jobs WHERE job_id=?",
        (job_id,),
        fetchone=True
    )
    if not row:
        return None
    return {
        "job_id": row[0],
        "user_id": row[1],
        "chat_id": row[2],
        "tiktok_url": row[3],
        "status": row[4],
        "verified": bool(row[5]),
        "created_at": row[6]
    }

def mark_job_verified(job_id: str):
    _db_exec(
        "UPDATE ad_jobs SET verified=1, status='verified', verified_at=? WHERE job_id=?",
        (int(time.time()), job_id)
    )

# ============ TELEGRAM API ============
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
        "lang_set": "✅ Language set to <b>English</b>\n\nNow send your TikTok link.",
        "send_link": "❌ Please send a valid TikTok link.",
        "link_received": "✅ TikTok link saved!\n\n👇 Choose below:",
        "verified": "✅ Ad verified! Choose format:",
        "premium_ok": "✅ LIFETIME Premium activated! No ads ever! 🎉",
        "premium_desc": "Remove ads FOREVER - Download unlimited videos!",
        "processing": "⏳ Downloading...",
        "premium_active": "⭐ You have LIFETIME Premium! No ads needed.",
    },
    "am": {
        "welcome": "🌐 <b>ቋንቋዎን ይምረጡ:</b>",
        "lang_set": "✅ ቋንቋ ወደ <b>አማርኛ</b> ተቀይሯል\n\nአሁን የTikTok ሊንክ ይላኩ።",
        "send_link": "❌ እባክዎ ትክክለኛ TikTok ሊንክ ይላኩ።",
        "link_received": "✅ TikTok ሊንክ ተወስጇል!\n\n👇 ከዚህ በታች ይምረጡ:",
        "verified": "✅ ad ተረጋገጠ! ቅርጸት ይምረጡ:",
        "premium_ok": "✅ ለዕለት ፕሪሚየም ነቅተዋል! ምንም ads ሌላ! 🎉",
        "premium_desc": "ቢሌንዚስ ወዲ ምንም ads - ማግኔታውያን ቪዲዮወች ያወርዱ!",
        "processing": "⏳ ያወርዳል...",
        "premium_active": "⭐ LIFETIME Premium ተሰጥቶዎታል! ads ሌላ።",
    },
    "om": {
        "welcome": "🌐 <b>Afaan filadhu:</b>",
        "lang_set": "✅ Afaan <b>Afaan Oromoo</b> irra jijjiirame\n\nHar'a linki TikTok ergaa.",
        "send_link": "❌ Maaloo linki TikTok sirrii ergaa.",
        "link_received": "✅ Linki TikTok qabsiisuun guutame!\n\n👇 Armaan gaditti filadu:",
        "verified": "✅ Ad mirkanaa'e! Akaamsaa filadu:",
        "premium_ok": "✅ Preemiyam LIFETIME hewaa! adsota hin jiru! 🎉",
        "premium_desc": "Adsota hir'isuudhaan viidiyoota infiniteetti gad fageenyaa!",
        "processing": "⏳ Gad fageenyaa...",
        "premium_active": "⭐ Preemiyam LIFETIME qabdu! adsota hin jiru.",
    },
}

# ============ KEYBOARD WITH COLORS ============
def make_language_keyboard():
    """VERTICAL language buttons - each on separate line"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇹 Amharic (አማርኛ)", callback_data="lang_am")],
        [InlineKeyboardButton("🌍 Afaan Oromoo", callback_data="lang_om")],
    ])

def make_ad_gate_keyboard(job_id: str):
    """Ad gate with colored buttons"""
    ad_url = f"{AD_PAGE_URL}?user_id={{user_id}}&job_id={job_id}&link={{link}}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Watch Ad (15 sec)", url=ad_url)],
        [InlineKeyboardButton("⭐ Lifetime Premium (100⭐)", callback_data="buy_lifetime")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def make_quality_keyboard():
    """Quality selection - VERTICAL"""
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
    try:
        dl_url = call_tikwm_api(tiktok_url, mode) if TIKWM_API_URL else None
        tmp_filename = None
        
        if dl_url:
            ext = "mp3" if mode == "audio" else "mp4"
            tmp_filename = f"/tmp/{user_id}_{int(time.time())}.{ext}"
            with requests.get(dl_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp_filename, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
            send_file_via_bot(chat_id, tmp_filename, file_type="audio" if mode == "audio" else "video", caption="✅ Here is your file!")
        else:
            if mode == "audio":
                out_path = f"/tmp/{user_id}_{int(time.time())}.%(ext)s"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=True)
                found = out_path.replace(".%(ext)s", ".mp3")
                if os.path.exists(found):
                    send_file_via_bot(chat_id, found, file_type="audio", caption="✅ Here is your audio (MP3)!")
                    tmp_filename = found
            else:
                out_path = f"/tmp/{user_id}_{int(time.time())}.mp4"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=False)
                if os.path.exists(out_path):
                    send_file_via_bot(chat_id, out_path, file_type="video", caption="✅ Here is your video!")
                    tmp_filename = out_path
        
        if tmp_filename and os.path.exists(tmp_filename):
            os.remove(tmp_filename)
    except Exception as e:
        try:
            send_telegram_message(chat_id, f"❌ Error: {str(e)[:100]}")
        except Exception:
            pass

# ============ BOT HANDLERS ============
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    get_user(user_id)  # Create user if not exists
    
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
    
    user = get_user(user_id)
    lang = user.get("language", "en")
    if lang not in LANG_STRINGS:
        lang = "en"
    strings = LANG_STRINGS[lang]

    # Language selection
    if data.startswith("lang_"):
        lang_code = data.split("_", 1)[1]
        if lang_code not in LANG_STRINGS:
            lang_code = "en"
        set_user_language(user_id, lang_code)
        strings = LANG_STRINGS.get(lang_code, LANG_STRINGS["en"])
        answer_callback_query(query.id, f"✅ Language set!")
        send_telegram_message(chat_id, strings["lang_set"])
        return

    if data == "cancel":
        answer_callback_query(query.id, "Cancelled.")
        try:
            query.edit_message_text("❌ Operation cancelled.")
        except Exception:
            pass
        return

    # Buy LIFETIME Premium (100 Telegram Stars)
    if data == "buy_lifetime":
        answer_callback_query(query.id, "Opening payment...")
        await context.bot.send_invoice(
            chat_id=chat_id,
            title="LIFETIME Premium Pass",
            description=strings["premium_desc"],
            payload="lifetime_premium",
            provider_token="",  # Empty for Telegram Stars
            currency="XTR",
            prices=[LabeledPrice("LIFETIME Premium", 10000)]  # 100 Telegram Stars = 10000 (in cents)
        )
        return

    # Quality selection (AFTER AD VERIFIED OR HAS PREMIUM)
    if data.startswith("quality_"):
        choice = data.split("_", 1)[1]
        user = get_user(user_id)
        tiktok_url = user.get("last_tiktok_url")
        if not tiktok_url:
            answer_callback_query(query.id, "❌ No link found.", alert=True)
            return
        
        answer_callback_query(query.id, strings["processing"])
        threading.Thread(target=process_download_job, args=(chat_id, user_id, tiktok_url, choice), daemon=True).start()
        return

    answer_callback_query(query.id, "")

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    user = get_user(user_id)
    lang = user.get("language", "en")
    if lang not in LANG_STRINGS:
        lang = "en"
    strings = LANG_STRINGS[lang]
    
    # Grant LIFETIME premium
    set_user_premium(user_id)
    
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
        
        # Check if user has premium
        if user_has_premium(user_id):
            send_telegram_message(
                chat_id,
                strings["premium_active"] + "\n\n" + strings["verified"],
                reply_markup=make_quality_keyboard()
            )
        else:
            # User needs to watch ad or buy premium
            job_id = create_ad_job(user_id, chat_id, text)
            ad_gate = make_ad_gate_keyboard(job_id)
            send_telegram_message(chat_id, strings["link_received"], reply_markup=ad_gate)
        return

    send_telegram_message(chat_id, strings["send_link"])

# ============ FLASK ENDPOINTS ============
@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": int(time.time())})

@flask_app.route("/verify_ad", methods=["POST"])
def verify_ad():
    """Backend endpoint called by index.html after 15 seconds"""
    try:
        data = request.get_json()
        job_id = data.get("job_id")
        user_id = data.get("user_id")
        
        job = get_ad_job(job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found"}), 404
        
        if job["user_id"] != user_id:
            return jsonify({"success": False, "error": "User mismatch"}), 403
        
        # Mark as verified
        mark_job_verified(job_id)
        
        # Grant 24-hour pass (just for this download)
        # User can watch more ads or buy premium for unlimited
        
        return jsonify({"success": True, "message": "Ad verified!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@flask_app.route("/get_job/<job_id>", methods=["GET"])
def get_job(job_id):
    """Check job status"""
    try:
        job = get_ad_job(job_id)
        if not job:
            return jsonify({"success": False}), 404
        return jsonify({"success": True, "job": job})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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

    print("🤖 Bot started with ad verification & LIFETIME premium!")
    application.run_polling()

if __name__ == "__main__":
    main()
