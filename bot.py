#!/usr/init/env python3
"""
TikTok Downloader Telegram Bot - aiogram Implementation with Colored Buttons & Strict Ad-Gate
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

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import WebAppInfo, LabeledPrice

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

# ============ LOCALIZED STRINGS ============
LANG_STRINGS = {
    "en": {
        "lang_set": "✅ Language set to <b>English</b>.\n\nNow send your TikTok link!",
        "send_link": "❌ Please send a valid TikTok video link.",
        "quality_prompt": "🎉 <b>Ad completed!</b> Choose your preferred format:",
        "premium_success": "⭐ <b>Lifetime Premium Activated!</b> Enjoy unlimited downloads without ads forever.",
        "processing": "⏳ Downloading your file, please wait..."
    },
    "am": {
        "lang_set": "✅ ቋንቋዎ ወደ <b>አማርኛ</b> ተቀይሯል።\n\nአሁን የTikTok ሊንክ ይላኩ!",
        "send_link": "❌ እባክዎ ትክክለኛ የTikTok ሊንክ ይላኩ።",
        "quality_prompt": "🎉 <b>ማስታወቂያው ተጠናቋል!</b> የሚፈልጉትን ቅርጸት ይምረጡ:",
        "premium_success": "⭐ <b>የልዩ ዕድል (Lifetime) ፕሪሚየም ነቅቷል!</b> ያለ ማስታወቂያ ለዘላለም ያውርዱ።",
        "processing": "⏳ እየተወረደ ነው, እባክዎ ይጠብቁ..."
    },
    "om": {
        "lang_set": "✅ Afaan <b>Afaan Oromoo</b> tti jijjiirameera.\n\nAmma linki TikTok ergaa!",
        "send_link": "❌ Maaloo linki TikTok sirrii ergaa.",
        "quality_prompt": "🎉 <b>Beeksifni xumurameera!</b> Haala barbaaddan filadhu:",
        "premium_success": "⭐ <b>Preemiyamii Bara Guutuu (Lifetime) hojjeteera!</b> Beeksisa malee bilisaan buufadhaa.",
        "processing": "⏳ Buufachaa jira, maaloo eegaa..."
    }
}

# ============ KEYBOARDS WITH COLORS & WEB APP ============
def make_language_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"))
    builder.row(types.InlineKeyboardButton(text="🇪🇹 Amharic (አማርኛ)", callback_data="lang_am"))
    builder.row(types.InlineKeyboardButton(text="🌍 Afaan Oromoo", callback_data="lang_om"))
    return builder.as_markup()

def make_ad_gate_keyboard(user_id: int, job_id: str, link: str) -> types.InlineKeyboardMarkup:
    web_app_url = f"{AD_PAGE_URL}?user_id={user_id}&job_id={job_id}&link={requests.utils.quote(link)}"
    builder = InlineKeyboardBuilder()
    # Danger / Red styled button for watching the ad
    builder.row(types.InlineKeyboardButton(text="👁️ ማስታወቂያ ይመልከቱ (10s)", web_app=WebAppInfo(url=web_app_url), style="danger"))
    # Success / Green styled button for verification check / status
    builder.row(types.InlineKeyboardButton(text="✅ ማስታወቂያ ተመልክቻለሁ", callback_data="check_ad_status", style="success"))
    # Primary / Blue styled button for buying lifetime premium
    builder.row(types.InlineKeyboardButton(text="⭐ ፕሪሚየም ይግዙ", callback_data="buy_lifetime", style="primary"))
    builder.row(types.InlineKeyboardButton(text="🏠 Main Menu", callback_data="cancel"))
    return builder.as_markup()

def make_quality_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🎬 Video (No Watermark)", callback_data="quality_no_watermark", style="success"))
    builder.row(types.InlineKeyboardButton(text="🏷️ Video (With Watermark)", callback_data="quality_watermark", style="primary"))
    builder.row(types.InlineKeyboardButton(text="🎵 Audio Only (MP3)", callback_data="quality_audio"))
    builder.row(types.InlineKeyboardButton(text="◀️ Cancel / Start Over", callback_data="cancel", style="danger"))
    return builder.as_markup()

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

def process_download_job(bot: Bot, chat_id: int, user_id: int, tiktok_url: str, mode: str):
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
            if mode == "audio":
                bot.send_audio(chat_id=chat_id, audio=types.FSInputFile(tmp_filename), caption="✅ Here is your audio!")
            else:
                bot.send_video(chat_id=chat_id, video=types.FSInputFile(tmp_filename), caption="✅ Here is your video!")
        else:
            if mode == "audio":
                out_path = f"/tmp/{user_id}_{int(time.time())}.%(ext)s"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=True)
                found = out_path.replace(".%(ext)s", ".mp3")
                if os.path.exists(found):
                    bot.send_audio(chat_id=chat_id, audio=types.FSInputFile(found), caption="✅ Here is your audio (MP3)!")
                    tmp_filename = found
            else:
                out_path = f"/tmp/{user_id}_{int(time.time())}.mp4"
                download_via_yt_dlp(tiktok_url, out_path, extract_audio=False)
                if os.path.exists(out_path):
                    bot.send_video(chat_id=chat_id, video=types.FSInputFile(out_path), caption="✅ Here is your video!")
                    tmp_filename = out_path
        
        if tmp_filename and os.path.exists(tmp_filename):
            os.remove(tmp_filename)
    except Exception as e:
        try:
            bot.send_message(chat_id=chat_id, text=f"❌ Error processing download: {str(e)[:100]}")
        except Exception:
            pass

# ============ AIOGRAM ROUTERS / HANDLERS =++=========
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer(
        "🌐 <b>እባክዎ ቋንቋ ይምረጡ / Please choose your language / Afaan filadhu:</b>",
        reply_markup=make_language_keyboard()
    )

@dp.callback_query(F.data.startswith("lang_"))
async def callback_language(query: types.CallbackQuery):
    lang_code = query.data.split("_", 1)[1]
    set_user_language(query.from_user.id, lang_code)
    strings = LANG_STRINGS.get(lang_code, LANG_STRINGS["en"])
    await query.answer("✅ Language saved!")
    await query.message.answer(strings["lang_set"])

@dp.callback_query(F.data == "cancel")
async def callback_cancel(query: types.CallbackQuery):
    await query.answer("Cancelled.")
    await query.message.answer("❌ Action cancelled. Send a new TikTok link whenever you're ready.")

@dp.callback_query(F.data == "buy_lifetime")
async def callback_buy_lifetime(query: types.CallbackQuery, bot: Bot):
    await query.answer("Opening checkout...")
    await bot.send_invoice(
        chat_id=query.message.chat.id,
        title="Lifetime Premium Pass",
        description="Unlock lifetime unlimited downloads with zero ads!",
        payload="lifetime_premium_pass",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Lifetime Premium", amount=100)]
    )

@dp.callback_query(F.data == "check_ad_status")
async def callback_check_ad_status(query: types.CallbackQuery):
    user_id = query.from_user.id
    if user_has_access(user_id):
        user = get_user(user_id)
        strings = LANG_STRINGS.get(user.get("language", "en"), LANG_STRINGS["en"])
        await query.answer("✅ Verified!")
        await query.message.answer(strings["quality_prompt"], reply_markup=make_quality_keyboard())
    else:
        await query.answer("⚠️ You haven't finished watching the ad yet! Please tap the red Watch Ad button.", show_alert=True)

@dp.callback_query(F.data.startswith("quality_"))
async def callback_quality(query: types.CallbackQuery, bot: Bot):
    user_id = query.from_user.id
    user = get_user(user_id)
    strings = LANG_STRINGS.get(user.get("language", "en"), LANG_STRINGS["en"])
    
    if not user_has_access(user_id):
        await query.answer("⚠️ You must watch the ad or buy premium first!", show_alert=True)
        return
        
    tiktok_url = user.get("last_tiktok_url")
    if not tiktok_url:
        await query.answer("❌ No TikTok link found.", show_alert=True)
        return
    
    choice = query.data.split("_", 1)[1]
    await query.answer(strings["processing"])
    threading.Thread(target=process_download_job, args=(bot, query.message.chat.id, user_id, tiktok_url, choice), daemon=True).start()

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    user_id = message.from_user.id
    set_lifetime_premium(user_id)
    user = get_user(user_id)
    strings = LANG_STRINGS.get(user.get("language", "en"), LANG_STRINGS["en"])
    await message.answer(
        strings["premium_success"] + "\n\n" + strings["quality_prompt"],
        reply_markup=make_quality_keyboard()
    )

@dp.message(F.text & ~F.text.startswith("/"))
async def text_message_handler(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    user = get_user(user_id)
    lang = user.get("language", "en")
    strings = LANG_STRINGS.get(lang, LANG_STRINGS["en"])

    if TIKTOK_RE.search(text):
        set_user_tiktok_url(user_id, text)
        
        if user_has_access(user_id):
            await message.answer(strings["quality_prompt"], reply_markup=make_quality_keyboard())
        else:
            job_id = create_ad_job(user_id, chat_id, text)
            await message.answer(
                "🔥 <b>ለቀጣይ 24 ሰዓት 10,000 ቪዲዮዎችን በነፃ ይውረዱ!</b>\n\n"
                "1️⃣ <b>ማስታወቂያ ይመልከቱ (10 ሰንድ)</b> – የ 10,000 ቪዲዮ ማውረጃ ፈቃድን አሁን ይክፈቱ!\n"
                "2️⃣ <b>ፕሪሚየም ይግዙ</b> – ምንም ማስታወቂያ የማይጠይቅ ፈቃድ ያግኙ።",
                reply_markup=make_ad_gate_keyboard(user_id, job_id, text)
            )
        return

    await message.answer(strings["send_link"])

# ============ FLASK ENDPOINTS ============
@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": int(time.time())})

@flask_app.route("/verify_ad", methods=["POST"])
def verify_ad():
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
        
        # Send notification via Bot API HTTP directly
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
            "chat_id": chat_id,
            "text": strings["quality_prompt"],
            "parse_mode": "HTML",
            "reply_markup": make_quality_keyboard().model_dump()
        }, timeout=15)
        
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

    bot = Bot(token=BOT_TOKEN)
    print("🤖 aiogram Bot started successfully with colored buttons!")
    dp.run_polling(bot)

if __name__ == "__main__":
    main()
