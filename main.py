import telebot
from config import BOT_TOKEN
from handlers import register_handlers

bot = telebot.TeleBot(BOT_TOKEN)

# Register all handlers
register_handlers(bot)

if __name__ == "__main__":
    print("Bot is running cleanly with modular files...")
    bot.infinity_polling()
