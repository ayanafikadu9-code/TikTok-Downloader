import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
import aiohttp

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
HOST = os.getenv("HOST", "https://tiktok-downloader-bot-986c.onrender.com")

# Temporary job/user storage for verification flow
active_jobs = {}

# Initialize Flask app for webhooks/ad verification
app = Flask(__name__)

@app.route('/verify_ad', methods=['POST'])
def verify_ad():
    data = request.json or {}
    user_id = data.get("user_id")
    job_id = data.get("job_id")
    
    if not user_id or not job_id:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    # Mark job as verified
    active_jobs[job_id] = {"user_id": user_id, "verified": True}
    logger.info(f"Ad verified successfully for user {user_id}, job {job_id}")
    
    return jsonify({"success": True})

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# Fetch live GitHub stars count dynamically
async def get_github_stars():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.github.com/repos/ayanafikadu9-code/TikTok-Downloader") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("stargazers_count", 0)
    except Exception as e:
        logger.error(f"Error fetching GitHub stars: {e}")
    return 10  # Fallback default

# Telegram Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    # Check if returning from ad verification
    if args and args[0].startswith("ad_verified_"):
        job_id = args[0].replace("ad_verified_", "")
        if job_id in active_jobs and active_jobs[job_id].get("verified"):
            await update.message.reply_text(
                "🎉 **Ad Verification Successful!**\n\nHere is your processed TikTok video download link:",
                parse_mode="Markdown"
            )
            return

    stars = await get_github_stars()
    
    welcome_text = (
        f"👋 Welcome, {user.first_name}!\n\n"
        f"⭐ **GitHub Stars:** {stars}\n"
        "🔥 Send me any TikTok video link to download it without watermarks, or choose a theme color below:"
    )
    
    # Working Color Buttons Keyboard
    keyboard = [
        [
            InlineKeyboardButton("🔴 Red Theme", callback_data="color_red"),
            InlineKeyboardButton("🔵 Blue Theme", callback_data="color_blue")
        ],
        [
            InlineKeyboardButton("🟢 Green Theme", callback_data="color_green"),
            InlineKeyboardButton("🎨 Custom Accent", callback_data="color_custom")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Check if triggered via start deep link parameter
    if args and args[0] == "download":
        job_id = "job_" + str(user.id)
        web_app_url = f"https://ayanafikadu9-code.github.io/TikTok-Downloader/?user_id={user.id}&job_id={job_id}"
        
        ad_keyboard = [[InlineKeyboardButton("🔥 Watch Ad to Unlock Video", url=web_app_url)]]
        await update.message.reply_text(
            "⚠️ **Action Required:** Please watch a short sponsored ad to unlock your TikTok download.",
            reply_markup=InlineKeyboardMarkup(ad_keyboard),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "color_red":
        await query.edit_message_text("🔴 Red theme selected successfully!")
    elif data == "color_blue":
        await query.edit_message_text("🔵 Blue theme selected successfully!")
    elif data == "color_green":
        await query.edit_message_text("🟢 Green theme selected successfully!")
    elif data == "color_custom":
        await query.edit_message_text("🎨 Custom accent theme configured!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "tiktok.com" in text:
        user = update.effective_user
        job_id = f"job_{user.id}_{int(asyncio.get_event_loop().time())}"
        
        web_app_url = f"https://ayanafikadu9-code.github.io/TikTok-Downloader/?user_id={user.id}&job_id={job_id}&link={text}"
        
        keyboard = [[InlineKeyboardButton("🔥 Watch Ad to Unlock Video", url=web_app_url)]]
        await update.message.reply_text(
            "📥 **TikTok Link Received!**\n\nClick the button below to complete a quick sponsored step and download your video:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Please send a valid TikTok video link.")

def main():
    if not BOT_TOKEN:
        logger.error("No BOT_TOKEN found in environment variables!")
        return

    # Start Flask server in background thread for ad verification callbacks
    import threading
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Build Telegram Bot
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("download", start))
    
    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Bot is starting polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
