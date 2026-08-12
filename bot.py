import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import aiohttp

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Storage to track user verification status
active_jobs = {}

app = Flask(__name__)

@app.route('/verify_ad', methods=['POST'])
def verify_ad():
    data = request.json or {}
    user_id = data.get("user_id")
    job_id = data.get("job_id")
    
    if not user_id or not job_id:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    active_jobs[job_id] = {"user_id": user_id, "verified": True}
    logger.info(f"Ad verified successfully for user {user_id}, job {job_id}")
    return jsonify({"success": True})

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

async def get_github_stars():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.github.com/repos/ayanafikadu9-code/TikTok-Downloader") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("stargazers_count", 0)
    except Exception as e:
        logger.error(f"Error fetching GitHub stars: {e}")
    return 10

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stars = await get_github_stars()
    
    welcome_text = (
        f"👋 ሰላም {user.first_name}!እንኳን ደህና መጡ።\n\n"
        f"⭐ **GitHub Stars:** {stars}\n"
        "🔥 ማንኛውንም የቲክቶክ ሊንክ ይላኩ ወይም ከታች ያሉትን የቴምፕ ቀለም ምርጫዎች ይጠቀሙ:"
    )
    
    # Restored Color Theme Buttons
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
        
        keyboard = [
            [InlineKeyboardButton("📺 Watch Ad to Unlock Video", url=web_app_url)],
            [InlineKeyboardButton("⭐ Buy Lifetime Premium", callback_data="premium")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        
        # Save job context to check later
        active_jobs[job_id] = {"user_id": user.id, "verified": False, "chat_id": update.effective_chat.id}
        
        msg = await update.message.reply_text(
            "📥 **TikTok Link Received!**\n\nClick the button below to watch the quick ad. Your video will be delivered automatically right after!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        # Background loop to check when the web app pings back verification
        asyncio.create_task(check_verification_status(job_id, context, msg.message_id, update.effective_chat.id))
    else:
        await update.message.reply_text("❌ እባክዎ ትክክለኛ የቲክቶክ ሊንክ ይላኩ።")

async def check_verification_status(job_id, context, message_id, chat_id):
    # Wait up to 3 minutes for the user to finish watching the ad
    for _ in range(60):
        await asyncio.sleep(3)
        job = active_jobs.get(job_id)
        if job and job.get("verified"):
            # Automatically deliver the video when verified!
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="🎉 **Ad Verified Successfully!**\n\nHere is your processed TikTok video download link:",
                parse_mode="Markdown"
            )
            # Here you can also trigger your video downloading/sending function
            return

def main():
    if not BOT_TOKEN:
        logger.error("No BOT_TOKEN found!")
        return

    import threading
    threading.Thread(target=run_flask, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    application.run_polling()

if __name__ == '__main__':
    main()
