#!/usr/bin/env python3
"""
TikTok Downloader Telegram Bot - Cleaned & Production-Ready for Render
"""

import os
import re
import time
import sqlite3
import secrets
import threading
import subprocess
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

HOST = os.getenv("HOST", "https://tiktok-downloader-z10d.onrender.com")
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
                is_lifetime_premium BOOLEAN DEFAULT 0,
                pass_expires_at INTEGER
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
        "SELECT user_id, language, last_tiktok_url, is_lifetime_premium, pass_expires_at FROM users WHERE user_id=?",
        (user_id,),
        fetchone=True
    )
    if not row:
        _db_exec("INSERT OR IGNORE INTO users (user_id, language) VALUES (?, ?)", (user_id, "en"))
        return {"user_id": user_id, "language": "en", "last_tiktok_url": None, "is_lifetime_premium": False, "pass_expires_at": None}
    return {
        "user_id": row[0],
        "language": row[1] or "en",
        "last_tiktok_url": row[2],
        "is_lifetime_premium": bool(row[3]),
        "pass_expires_at": row[4]
    }

def set_user_tiktok_url(user_id: int, url: str):
    _db_exec("UPDATE users SET last_tiktok_url=? WHERE user_id=?", (url, user_id))

def set_lifetime_premium(user_id: int):
    _db_exec("UPDATE users SET is_lifetime_premium=1 WHERE user_id=?", (user_id,))

def grant_temporary_pass(user_id: int, duration_hours: int = 24):
    expires = int(time.time()) + (duration_hours * 3600)
    _db_exec("UPDATE users SET pass_expires_at=? WHERE user_id=?", (expires, user_id))

def user_has_access(user_id: int) -> bool:
    u = get_user(user_id)
    if u.get("is_lifetime_premium"):
        return True
    expires = u.get("pass_expires_at")
    if expires and int(time.time()) < expires:
        return True
    return False

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
    _db_exec("UPDATE ad_jobs SET verified=1, status='verified' WHERE job_id=?", (job_id,))

# ============ TELEGRAM API HELPERS ============
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

# ============ LOCALIZED STRINGS ============
LANG_STRINGS = {
    "en": {
        "welcome": "🌐 <b>Please choose your language:</b>",
        "lang_set": "✅ Language set to <b>English</b>.\n\nNow send your TikTok link!",
        "send_link": "❌ Please send a valid TikTok video link.",
        "link_received": "📥 <b>TikTok link received!</b>\n\nChoose an option below to proceed:",
        "quality_prompt": "🎉 <b>Ad completed!</b> Choose your preferred format:",
        "premium_success": "⭐ <b>Lifetime Premium Activated!</b> Enjoy unlimited downloads without ads forever.",
        "processing": "⏳ Downloading your file, please wait..."
    },
    "am": {
        "welcome": "🌐 <b>እባክዎ ቋንቋዎን ይምረጡ:</b>",
        "lang_set": "✅ ቋንቋዎ ወደ <b>አማርኛ</b> ተቀይሯል።\n\nአሁን የTikTok ሊንክ ይላኩ!",
        "send_link": "❌ እባክዎ ትክክለኛ የTikTok ሊንክ ይላኩ።",
        "link_received": "📥 <b>የTikTok ሊንክ ተቀብለናል!</b>\n\nከታች ካሉት አማራጮች አንዱን ይምረጡ:",
        "quality_prompt": "🎉 <b>ማስታወቂያው ተጠናቋል!</b> የሚፈልጉትን ቅርጸት ይምረጡ:",
        "premium_success": "⭐ <b>የልዩ ዕድል (Lifetime) ፕሪሚየም ነቅቷል!</b> ያለ ማስታወቂያ ለዘላለም ያውርዱ።",
        "processing": "⏳ እየተወረደ ነው, እባክዎ ይጠብቁ..."
    },
    "om": {
        "welcome": "🌐 <b>Maaloo afaan filadhu:</b>",
        "lang_set": "✅ Afaan <b>Afaan Oromoo</b> tti jijjiirameera.\n\nAmma linki TikTok ergaa!",
        "send_link": "❌ Maaloo linki TikTok sirrii ergaa.",
        "link_received": "📥 <b>Linki TikTok argameera!</b>\n\nFilannoo armaan gadቲ irraa filadhu:",
        "quality_prompt": "🎉 <b>Beeksifni xumurameera!</b> Haala barbaaddan filadhu:",
        "premium_success": "⭐ <b>Preemiyamii Bara Guutuu (Lifetime) hojjeteera!</b> Beeksisa malee bilisaan buufadhaa.",
        "processing": "⏳ Buufachaa jira, maaloo eegaa..."
    }
}

# ============ KEYBOARDS ============
def make_language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇹 Amharic (አማርኛ)", callback_data="lang_am")],
        [InlineKeyboardButton("🌍 Afaan Oromoo", callback_data="lang_om")],
    ])

def make_ad_gate_keyboard(user_id: int, job_id: int, link: str):
    ad_url = f"{AD_PAGE_URL}?user_id={user_id}&job_id={job_id}&link={requests.utils.quote(link)}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Watch Ad (15s)", url=ad_url)],
        [InlineKeyboardButton("⭐ Buy Lifetime Premium (100 ⭐️)", callback_data="buy_lifetime")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def make_quality_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Video (No Watermark)", callback_data="quality_no_watermark")],
        [InlineKeyboardButton("🏷️ Video (With Watermark)", callback_data="quality_watermark")],
        [InlineKeyboardButton("🎵 Audio Only (MP3)", callback_data="quality_audio")],
        [InlineKeyboardButton("◀️ Cancel / Start Over", callback_data="cancel")],
    ])

# ============ DOWNLOAD HANDLERS ============
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
            send_telegram_message(chat_id, f"❌ Error processing download: {str(e)[:100]}")
        except Exception:
            pass

# ============ BOT HANDLERS ============
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    get_user(user_id)
    
    send_telegram_message(
        chat_id,
        "🌐 <b>Please choose your language / እባክዎ ቋንቋ ይምረጡ / Afaan filadhu:</b>",
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
    strings = LANG_STRINGS.get(lang, LANG_STRINGS["en"])

    if data.startswith("lang_"):
        lang_code = data.split("_", 1)[1]
        set_user_language(user_id, lang_code)
        new_strings = LANG_STRINGS.get(lang_code, LANG_STRINGS["en"])
        answer_callback_query(query.id, "✅ Language saved!")
        send_telegram_message(chat_id, new_strings["lang_set"])
        return

    if data == "cancel":
        answer_callback_query(query.id, "Cancelled.")
        try:
            query.edit_message_text("❌ Action cancelled. Send a new TikTok link anytime.")
        except Exception:
            pass
        return

    if data == "buy_lifetime":
        answer_callback_query(query.id, "Opening checkout...")
        await context.bot.send_invoice(
            chat_id=chat_id,
            title="Lifetime Premium Pass",
            description="Unlock lifetime unlimited downloads with zero ads!",
            payload="lifetime_premium_pass",
            provider_token="",  # Telegram Stars
            currency="XTR",
            prices=[LabeledPrice("Lifetime Premium", 100)]  # 100 Stars
        )
        return

    if data.startswith("quality_"):
        choice = data.split("_", 1)[1]
        if not user_has_access(user_id):
            answer_callback_query(query.id, "Please watch the ad or buy premium first.", alert=True)
            return
            
        tiktok_url = user.get("last_tiktok_url")
        if not tiktok_url:
            answer_callback_query(query.id, "❌ No TikTok link found.", alert=True)
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
    
    set_lifetime_premium(user_id)
    user = get_user(user_id)
    strings = LANG_STRINGS.get(user.get("language", "en"), LANG_STRINGS["en"])
    
    send_telegram_message(
        chat_id,
        strings["premium_success"] + "\n\n" + strings["quality_prompt"],
        reply_markup=make_quality_keyboard()
    )

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    user = get_user(user_id)
    lang = user.get("language", "en")
    strings = LANG_STRINGS.get(lang, LANG_STRINGS["en"])

    if TIKTOK_RE.search(text):
        set_user_tiktok_url(user_id, text)
        
        if user_has_access(user_id):
            send_telegram_message(
                chat_id,
                strings["quality_prompt"],
                reply_markup=make_quality_keyboard()
            )
        else:
            job_id = create_ad_job(user_id, chat_id, text)
            send_telegram_message(
                chat_id,
                strings["link_received"],
                reply_markup=make_ad_gate_keyboard(user_id, job_id, text)
            )
        return

    send_telegram_message(chat_id, strings["send_link"])

# ============ FLASK ENDPOINTS ============
@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": int(time.time())})

@flask_app.route("/verify_ad", methods=["POST"])
def verify_ad():
    """Called automatically by your GitHub Pages ad page after 15 seconds"""
    try:
        data = request.get_json() or {}
        job_id = data.get("job_id")
        user_id = data.get("user_id")
        
        job = get_ad_job(job_id)
        if not job:
            return jsonify({"success": False, "error": "Job not found"}), 404
        
        mark_job_verified(job_id)
        grant_temporary_pass(int(user_id), duration_hours=24)
        
        chat_id = job["chat_id"]
        user = get_user(int(user_id))
        strings = LANG_STRINGS.get(user.get("language", "en"), LANG_STRINGS["en"])
        
        send_telegram_message(
            chat_id,
            strings["quality_prompt"],
            reply_markup=make_quality_keyboard()
        )
        
        return jsonify({"success": True, "message": "Ad verified & quality menu sent!"})
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

    print("🤖 Bot started successfully!")
    application.run_polling()

if __name__ == "__main__":
    main()
