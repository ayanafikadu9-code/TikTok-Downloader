#!/usr/bin/env python3
"""
TikTok Downloader Telegram Bot
Features:
- /start -> language selection (English, Amharic, Afaan Oromoo)
- After language chosen -> ask user to send TikTok link
- When TikTok link received -> show ad gate:
    * URL button to your ad page (GitHub Pages)
    * "Verify / I have watched the ad" button (grants 24h pass)
    * "Buy Premium" button (links to premium page)
- After verify -> immediately show quality menu:
    * 🎬 Video (No Watermark)
    * 🏷️ Video (With Watermark)
    * 🎵 Audio Only (MP3)
- On selection -> attempt to get content from TikWM API (if configured) otherwise fallback to yt-dlp
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
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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
    _db_exec("INSERT INTO users (user_id, language) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET language=excluded.language", (user_id, lang))

def get_user(user_id: int) -> dict:
    row = _db_exec("SELECT user_id, language, last_tiktok_url, pass_expires_at FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not row:
        _db_exec("INSERT OR IGNORE INTO users (user_id, language) VALUES (?, ?)", (user_id, "en"))
        return {"user_id": user_id, "language": "en", "last_tiktok_url": None, "pass_expires_at": None}
    return {"user_id": row[0], "language": row[1] or "en", "last_tiktok_url": row[2], "pass_expires_at": row[3]}

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
    _db_exec("INSERT INTO jobs (job_id, user_id, tiktok_url, status, created_at) VALUES (?, ?, ?, ?, ?)", (job_id, user_id, tiktok_url, "pending", int(time.time())))
    return job_id

def update_job_status(job_id: str, status: str):
    _db_exec("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_raw_message(chat_id: int, text: str, reply_markup: Optional[dict] = None, parse_mode: Optional[str] = None):
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)
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

@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": int(time.time())})

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
        cmd = ["yt-dlp", "-o", out_path, "-f", "mp4", tiktok_url]
    subprocess.check_call(cmd, timeout=600)

def process_download_job(chat_id: int, user_id: int, tiktok_url: str, mode: str):
    job_id = create_job(user_id, tiktok_url)
    update_job_status(job_id, "started")
    try:
        dl_url = call_tikwm_api(tiktok_url, mode) if TIKWM_API_URL else None
        tmp_filename = None
        if dl_url:
            ext = "mp3" if mode == "audio" else "mp4"
            tmp_filename = f"/tmp/{job_id}.{ext}"
            with requests.get(dl_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp_filename, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
            send_file_via_bot(chat_id, tmp_filename, file_type="audio" if mode == "audio" else "video", caption="Here is your file")
            update_job_status(job_id, "sent")
        else:
            if mode == "audio":
                out_path = f"/tmp/{job_id}.%(ext)s"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=True)
                found = f"/tmp/{job_id}.mp3"
                send_file_via_bot(chat_id, found, file_type="audio", caption="Here is your audio (MP3)")
                update_job_status(job_id, "sent")
                tmp_filename = found
            else:
                out_path = f"/tmp/{job_id}.mp4"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=False)
                send_file_via_bot(chat_id, out_path, file_type="video", caption="Here is your video")
                update_job_status(job_id, "sent")
                tmp_filename = out_path
        if tmp_filename and os.path.exists(tmp_filename):
            os.remove(tmp_filename)
    except Exception as e:
        update_job_status(job_id, "failed")
        try:
            send_raw_message(chat_id, f"Failed to process your request: {e}")
        except Exception:
            pass

LANG_BUTTONS = {"en": "English", "am": "Amharic (አማርኛ)", "om": "Afaan Oromoo"}

def make_language_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": f"🇬🇧 {LANG_BUTTONS['en']}", "callback_data": "lang_en", "style": "primary"},
                {"text": f"🇪🇹 {LANG_BUTTONS['am']}", "callback_data": "lang_am", "style": "primary"},
                {"text": f"🌍 {LANG_BUTTONS['om']}", "callback_data": "lang_om", "style": "primary"},
            ]
        ]
    }

def make_ad_gate_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🔗 Open Ad Page", "url": AD_PAGE, "style": "primary"},
                {"text": "✅ Verify / I have watched the ad", "callback_data": "verify_ad", "style": "success"},
            ],
            [
                {"text": "⭐ Buy Premium", "url": PREMIUM_URL, "style": "primary"},
                {"text": "❌ Cancel", "callback_data": "cancel", "style": "danger"},
            ],
        ]
    }

def make_quality_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🎬 Video (No Watermark)", "callback_data": "quality_no_watermark", "style": "primary"},
                {"text": "🏷️ Video (With Watermark)", "callback_data": "quality_watermark", "style": "primary"},
            ],
            [
                {"text": "🎵 Audio Only (MP3)", "callback_data": "quality_audio", "style": "primary"},
                {"text": "◀️ Cancel", "callback_data": "cancel", "style": "danger"},
            ],
        ]
    }

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    send_raw_message(update.effective_chat.id, "Welcome! Please choose your language / እባክዎ ቋንቋዎን ይምረጡ / Afaan filadhu", reply_markup=make_language_keyboard())

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    user_id = query.from_user.id
    chat_id = query.message.chat.id if query.message else user_id

    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        set_user_language(user_id, lang if lang in LANG_BUTTONS else "en")
        answer_callback_query(query.id, f"Language set.")
        send_raw_message(chat_id, f"Language set to {LANG_BUTTONS.get(lang,'English')}.\nNow please send your TikTok link.")
        return

    if data == "cancel":
        answer_callback_query(query.id, "Cancelled.")
        try:
            query.edit_message_text("Operation cancelled.")
        except Exception:
            pass
        return

    if data == "verify_ad":
        expires_at = int((datetime.utcnow() + timedelta(hours=24)).timestamp())
        set_user_pass(user_id, expires_at)
        answer_callback_query(query.id, "Verified — 24-hour pass granted ✅")
        send_raw_message(chat_id, "Verification accepted. Choose the output you want:", reply_markup=make_quality_keyboard())
        return

    if data.startswith("quality_"):
        if not user_has_valid_pass(user_id):
            answer_callback_query(query.id, "You need a valid pass. Please open the ad page and press Verify.", alert=True)
            return
        choice = data.split("_", 1)[1]
        u = get_user(user_id)
        tiktok_url = u.get("last_tiktok_url")
        if not tiktok_url:
            answer_callback_query(query.id, "No TikTok link found. Send your link first.", alert=True)
            return
        answer_callback_query(query.id, "Processing your request...")
        threading.Thread(target=process_download_job, args=(chat_id, user_id, tiktok_url, choice), daemon=True).start()
        return

    answer_callback_query(query.id, "")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if TIKTOK_RE.search(text):
        set_user_tiktok_url(user_id, text)
        send_raw_message(
            chat_id,
            "TikTok link saved! To continue, please open the ad page, watch, and press 'Verify / I have watched the ad'.",
            reply_markup=make_ad_gate_keyboard(),
        )
        return

    await update.message.reply_text("Please send a valid TikTok link.")

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

def run_flask():
    port = int(os.getenv("PORT", "5000"))
    flask_app.run(host="0.0.0.0", port=port, threaded=True)

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    if KEEPALIVE_ENABLED:
        threading.Thread(target=keepalive_loop, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    application.run_polling()

if __name__ == "__main__":
    main()
