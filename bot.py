#!/usr/bin/env python3
import os
import threading
import uuid
import secrets
import sqlite3
import time
import subprocess
import json
import requests

from flask import Flask, request, render_template_string, abort, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# Configuration (set these env vars in production)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "<YOUR_BOT_TOKEN>")
HOST = os.environ.get("HOST", "https://example.com")  # public URL for your server
AD_VIDEO_URL = os.environ.get("AD_VIDEO_URL", "https://www.w3schools.com/html/mov_bbb.mp4")  # sample ad video

# Optional custom emoji ids (use if you have them); otherwise leave empty
ICON_WATCH = os.environ.get("ICON_WATCH", "")      # icon_custom_emoji_id for Watch ad
ICON_PREMIUM = os.environ.get("ICON_PREMIUM", "")  # icon_custom_emoji_id for Premium

# Simple job store using sqlite for demo
conn = sqlite3.connect("jobs.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    chat_id INTEGER,
    tiktok_url TEXT,
    secret TEXT,
    status TEXT,
    created_at INTEGER
)""")
conn.commit()

app = Flask(__name__)

def save_job(job_id, chat_id, tiktok_url, secret):
    c.execute("INSERT INTO jobs (job_id, chat_id, tiktok_url, secret, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (job_id, chat_id, tiktok_url, secret, "pending", int(time.time())))
    conn.commit()

def get_job(job_id):
    c.execute("SELECT job_id, chat_id, tiktok_url, secret, status FROM jobs WHERE job_id=?", (job_id,))
    row = c.fetchone()
    if not row:
        return None
    return dict(job_id=row[0], chat_id=row[1], tiktok_url=row[2], secret=row[3], status=row[4])

def update_job_status(job_id, status):
    c.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))
    conn.commit()

# Ad page - shows a video and calls /ad-complete after 15s
AD_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Watch ad</title>
  </head>
  <body>
    <h3>Watch this short ad to get your video</h3>
    <video id="ad" width="480" controls autoplay>
      <source src="{{ ad_url }}" type="video/mp4">
      Your browser does not support the video tag.
    </video>
    <p id="status">Please watch at least 15 seconds...</p>
    <script>
      const jobId = "{{ job_id }}";
      const secret = "{{ secret }}";
      const ad = document.getElementById('ad');
      const status = document.getElementById('status');
      // Wait 15s regardless of video length
      setTimeout(() => {
        fetch("/ad-complete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: jobId, secret: secret })
        }).then(r => r.json()).then(j => {
          status.textContent = j.message || "Done. You can close this window.";
        }).catch(e => { status.textContent = "Error contacting server"; });
      }, 15000);
    </script>
  </body>
</html>
"""

@app.route("/ad")
def ad_page():
    job_id = request.args.get("job_id")
    secret = request.args.get("secret")
    if not job_id or not secret:
        abort(400)
    job = get_job(job_id)
    if not job or job["secret"] != secret:
        abort(404)
    return render_template_string(AD_HTML, ad_url=AD_VIDEO_URL, job_id=job_id, secret=secret)

@app.route("/ad-complete", methods=["POST"])
def ad_complete():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "message": "invalid json"}), 400
    job_id = data.get("job_id")
    secret = data.get("secret")
    job = get_job(job_id)
    if not job or job["secret"] != secret:
        return jsonify({"ok": False, "message": "invalid job"}), 404
    if job["status"] != "pending":
        return jsonify({"ok": True, "message": "already processed"})
    # mark as authorized
    update_job_status(job_id, "authorized")
    # kick off background worker to download and deliver
    threading.Thread(target=process_job_and_send, args=(job_id,), daemon=True).start()
    return jsonify({"ok": True, "message": "authorized, processing your video"})

def process_job_and_send(job_id):
    job = get_job(job_id)
    if not job:
        return
    update_job_status(job_id, "downloading")
    tiktok_url = job["tiktok_url"]
    chat_id = job["chat_id"]
    out_filename = f"{job_id}.mp4"
    ytdlp_cmd = ["yt-dlp", "-o", out_filename, "-f", "mp4", tiktok_url]
    try:
        subprocess.check_call(ytdlp_cmd, timeout=300)
    except Exception as e:
        update_job_status(job_id, "failed")
        send_message(chat_id, f"Failed to download video: {e}")
        return
    update_job_status(job_id, "uploading")
    try:
        send_video_file(chat_id, out_filename, caption="Here is your TikTok video")
        update_job_status(job_id, "done")
    except Exception as e:
        update_job_status(job_id, "failed")
        send_message(chat_id, f"Failed to send video: {e}")
    finally:
        try:
            os.remove(out_filename)
        except Exception:
            pass

def send_message(chat_id, text, reply_markup=None):
    """
    Sends a message using raw Bot API HTTP request. If reply_markup is provided,
    it should be a Python dict that will be JSON-serialized exactly (this allows using
    Bot API 9.4 fields such as 'style' and 'icon_custom_emoji_id').
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        # Bot API accepts reply_markup as JSON-serialized string; ensure it's serialized
        payload["reply_markup"] = json.dumps(reply_markup)
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()

def send_video_file(chat_id, file_path, caption=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    with open(file_path, "rb") as fh:
        files = {"video": fh}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        r = requests.post(url, data=data, files=files, timeout=120)
        r.raise_for_status()
    return r.json()

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send /download <tiktok_url> to start.")

async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /download <tiktok_url>")
        return
    tiktok_url = context.args[0]
    # Basic validation
    if "tiktok" not in tiktok_url:
        await update.message.reply_text("Please provide a TikTok URL.")
        return
    job_id = uuid.uuid4().hex
    secret = secrets.token_urlsafe(16)
    save_job(job_id, update.effective_chat.id, tiktok_url, secret)
    ad_url = f"{HOST}/ad?job_id={job_id}&secret={secret}"
    premium_url = f"{HOST}/premium"  # example premium link

    # Build inline keyboard using Bot API 9.4 fields (style + optional icon_custom_emoji_id)
    reply_markup = {
      "inline_keyboard": [
        [
          {
            "text": "Watch ad (15s)",
            "url": ad_url,
            "style": "success",
            # only include icon_custom_emoji_id when provided
            **({"icon_custom_emoji_id": ICON_WATCH} if ICON_WATCH else {})
          },
          {
            "text": "Cancel",
            "callback_data": "cancel",
            "style": "danger"
          }
        ],
        [
          {
            "text": "Get Premium",
            "url": premium_url,
            "style": "primary",
            **({"icon_custom_emoji_id": ICON_PREMIUM} if ICON_PREMIUM else {})
          }
        ]
      ]
    }

    # Send using raw Bot API so 'style' field is preserved
    send_message(update.effective_chat.id, "Click a button to continue", reply_markup=reply_markup)

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle callback query for 'cancel'
    query = update.callback_query
    if query:
        await query.answer("Cancelled.")
        # Optionally edit the message or update job status
        try:
            await query.edit_message_text("Operation cancelled by user.")
        except Exception:
            pass

def run_flask():
    # In production run behind a real WSGI server; this is for demo only
    app.run(host="0.0.0.0", port=5000)

def main():
    # Start Flask in background thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    # Start Telegram bot (long polling)
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("download", download_cmd))
    application.add_handler(CallbackQueryHandler(cancel_handler, pattern="^cancel$"))
    print("Bot started. Listening for commands.")
    application.run_polling()

if __name__ == "__main__":
    main()
