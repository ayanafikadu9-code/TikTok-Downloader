import threading
import telebot
from flask import Flask
from config import BOT_TOKEN
from handlers import register_handlers

bot = telebot.TeleBot(BOT_TOKEN)
register_handlers(bot)

# Create a tiny Flask app so Render Web Service detects an active port
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

if __name__ == "__main__":
    # Run Flask in a separate thread so it doesn't block the Telegram bot
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    print("Bot and Web Server running simultaneously...")
    bot.infinity_polling()
