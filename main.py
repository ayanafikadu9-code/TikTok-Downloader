import asyncio
import time
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, LabeledPrice, PreCheckoutQuery

# ============ CONFIGURATION ============
BOT_TOKEN = "8913902406:AAE5YB6XyXY4JBXbODODwOTl4P-dnV7T2rA"
API_URL = "https://silent-mud-7026.codeofsaladin.workers.dev/tiktok"
WEB_APP_URL = "https://ayanafikadu9-code.github.io/TikTok-Downloader/"
DB_FILE = "bot_data.db"
ADMIN_ID = 123456789  # ⚠️ Replace with your actual Telegram User ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ----------------------------------------------------
# DATABASE HELPERS
# ----------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'en',
            ad_pass_expiry INTEGER DEFAULT 0,
            tiktok_url TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT lang, ad_pass_expiry, tiktok_url FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"lang": row[0], "ad_pass_expiry": row[1], "tiktok_url": row[2]}
    return {"lang": "en", "ad_pass_expiry": 0, "tiktok_url": ""}

def set_user_attr(user_id, key, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    cursor.execute(f'UPDATE users SET {key} = ? WHERE user_id = ?', (value, user_id))
    conn.commit()
    conn.close()

def get_all_user_ids():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

init_db()

# ----------------------------------------------------
# ADMIN COMMANDS
# ----------------------------------------------------
@dp.message(Command("stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_all_user_ids()
    await message.reply(f"📊 **Bot Database Stats:**\n\nTotal Registered Users: **{len(users)}**", parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def admin_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        await message.reply("⚠️ **Usage:** `/broadcast Your message here`", parse_mode="Markdown")
        return

    broadcast_msg = command_parts[1]
    all_users = get_all_user_ids()
    status_msg = await message.reply(f"🚀 **Starting Broadcast to {len(all_users)} users...**", parse_mode="Markdown")
    
    success, fail = 0, 0
    for u_id in all_users:
        try:
            await bot.send_message(u_id, broadcast_msg, parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1

    report = f"📢 **Broadcast Completed!**\n\n✅ Success: **{success}**\n❌ Failed: **{fail}**\n👥 Total: **{len(all_users)}**"
    await status_msg.edit_text(report, parse_mode="Markdown")

# ----------------------------------------------------
# COMMAND: /start
# ----------------------------------------------------
@dp.message(Command("start"))
async def send_start(message: types.Message):
    u_id = message.from_user.id
    u_data = get_user_data(u_id)
    lang = u_data["lang"]

    if lang == "am":
        text_msg = "🎬 **እንኳን ወደ TikTok ማውረጃ በደህና መጡ!**\n\nቪዲዮ ለማውረድ የ TikTok ሊንክ ይላኩ።"
        btn_lang = "🌐 ቋንቋ ለመቀየር"
    elif lang == "om":
        text_msg = "🎬 **Baga gara Buufata TikTok Nageenyaan Dhuftan!**\n\nViidiyoo buufachuuf hidhaa TikTok ergaa."
        btn_lang = "🌐 Afaan Jijjiiruuf"
    else:
        text_msg = "🎬 **Welcome to TikTok Downloader Bot!**\n\nSend any TikTok link below to start."
        btn_lang = "🌐 Change Language"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_lang, callback_data="/btn_lang", style="primary")]
    ])
    await message.answer(text_msg, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# LANGUAGE SELECTION MENU
# ----------------------------------------------------
@dp.callback_query(F.data.in_(['/btn_lang', '/lang_en', '/lang_am', '/lang_om']))
async def handle_language(call: types.CallbackQuery):
    u_id = call.from_user.id
    if call.data == '/btn_lang':
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="/lang_en", style="primary"),
                InlineKeyboardButton(text="🇪🇹 አማርኛ", callback_data="/lang_am", style="primary")
            ],
            [InlineKeyboardButton(text="🇪🇹 Afaan Oromoo", callback_data="/lang_om", style="primary")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="/btn_home", style="danger")]
        ])
        await call.message.edit_text("🌐 **Please select your language / ቋንቋ ይምረጡ / Afaan filadhaa:**", reply_markup=markup, parse_mode="Markdown")
    else:
        selected_lang = call.data.replace('/lang_', '')
        set_user_attr(u_id, "lang", selected_lang)
        confirm_text = "✅ Language set to **English**."
        if selected_lang == "am":
            confirm_text = "✅ ቋንቋው በሁኔታው ወደ **አማርኛ** ተቀይሯል።"
        elif selected_lang == "om":
            confirm_text = "✅ Afaan gara **Afaan Oromotti** jijjiirameera."

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="/btn_home", style="primary")]
        ])
        await call.message.edit_text(confirm_text, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# LINK DETECTION (AD GATE & ACCESS CHECK)
# ----------------------------------------------------
@dp.message(F.text.contains("tiktok.com"))
async def handle_tiktok_link(message: types.Message):
    u_id = message.from_user.id
    current_time = int(time.time())
    set_user_attr(u_id, "tiktok_url", message.text.strip())
    
    u_data = get_user_data(u_id)
    lang = u_data["lang"]
    expiry_time = u_data["ad_pass_expiry"]

    if current_time >= expiry_time:
        if lang == "am":
            gate_msg = "🔥 **ቪዲዮ ለማውረድ ማስታወቂያ ይመልከቱ ወይም ፕሪሚየም ይግዙ:**"
            b_ad, b_verify, b_prem = "👁️ ማስታወቂያ ይመልከቱ (15s)", "✅ ማስታወቂያ አይቼአለሁ (አረጋግጥ)", "⭐ ፕሪሚየም ይግዙ (Telegram Stars)"
        elif lang == "om":
            gate_msg = "🔥 **Viidiyoo buufachuuf beeksisa daawwadhaa ykn piriimiyamii bitaa:**"
            b_ad, b_verify, b_prem = "👁️ Beeksisa Daawwadhaa (15s)", "✅ Beeksisa Daawwadhiree (Mirkaneessi)", "⭐ Piriimiyamii Bitaa (Telegram Stars)"
        else:
            gate_msg = "🔥 **To continue, watch a short ad or buy Premium:**"
            b_ad, b_verify, b_prem = "👉 Watch ad (15s)", "✅ I Watched the Ad (Verify)", "⭐ Buy Premium"

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=b_ad, web_app=WebAppInfo(url=WEB_APP_URL), style="success")],
            [InlineKeyboardButton(text=b_verify, callback_data="/check_ad_pass", style="primary")],
            [InlineKeyboardButton(text=b_prem, callback_data="/buy_premium", style="primary")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="/btn_home", style="danger")]
        ])
        await message.answer(gate_msg, reply_markup=markup, parse_mode="Markdown")
    else:
        await send_quality_options(message.chat.id, lang)

async def send_quality_options(chat_id, lang):
    if lang == "am":
        prompt_text = "🎥 **የማውረድ አማራጭ ይምረጡ:**"
        b_no_wm, b_wm, b_au = "🎬 ቪዲዮ (ያለ ዋተርማርክ)", "🏷️ ቪዲዮ (ከዋተርማርክ ጋር)", "🎵 ድምፅ ብቻ (MP3)"
    elif lang == "om":
        prompt_text = "🎥 **Filannoo buufata filadhaa:**"
        b_no_wm, b_wm, b_au = "🎬 Viidiyoo (Mallattoo Malee)", "🏷️ Viidiyoo (Mallattoo Wajjin)", "🎵 Sagalee Qofa (MP3)"
    else:
        prompt_text = "🎥 **Choose download option:**"
        b_no_wm, b_wm, b_au = "🎬 Video (No Watermark)", "🏷️ Video (With Watermark)", "🎵 Audio Only (MP3)"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b_no_wm, callback_data="quality_nowatermark", style="success")],
        [InlineKeyboardButton(text=b_wm, callback_data="quality_watermark", style="primary")],
        [InlineKeyboardButton(text=b_au, callback_data="quality_audio", style="primary")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="/btn_home", style="danger")]
    ])
    await bot.send_message(chat_id, prompt_text, reply_markup=markup, parse_mode="Markdown")

# ----------------------------------------------------
# WEB APP AD COMPLETION & MANUAL VERIFICATION
# ----------------------------------------------------
@dp.message(F.web_app_data)
async def handle_ad_completion(message: types.Message):
    u_id = message.from_user.id
    if message.web_app_data.data == "AD_COMPLETED":
        set_user_attr(u_id, "ad_pass_expiry", int(time.time()) + 86400)
        u_data = get_user_data(u_id)
        await message.answer("✅ **Ad verified! 24-Hour Pass Unlocked.**", parse_mode="Markdown")
        await send_quality_options(message.chat.id, u_data["lang"])

@dp.callback_query(F.data == '/check_ad_pass')
async def handle_manual_ad_check(call: types.CallbackQuery):
    u_id = call.from_user.id
    set_user_attr(u_id, "ad_pass_expiry", int(time.time()) + 86400)
    u_data = get_user_data(u_id)
    await call.message.edit_text("✅ **Ad pass unlocked! Select download quality below:**", parse_mode="Markdown")
    await send_quality_options(call.message.chat.id, u_data["lang"])

@dp.callback_query(F.data.in_(['/buy_premium', '/btn_home']))
async def handle_premium_menu(call: types.CallbackQuery):
    if call.data == '/btn_home':
        await send_start(call.message)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 1 month — 50 ⭐️ (30% OFF)", callback_data="buy_stars_50", style="primary")],
        [InlineKeyboardButton(text="🔥 3 months — 105 ⭐️ (30% OFF)", callback_data="buy_stars_105", style="success")],
        [InlineKeyboardButton(text="💎 12 months — 350 ⭐️ (30% OFF)", callback_data="buy_stars_350", style="primary")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="/btn_home", style="danger")]
    ])
    msg = (
        "🚫 **Remove ads**\n\n"
        "Download videos without mandatory ads or waiting.\n\n"
        "**Premium includes:**\n"
        "✅ No ads before downloads\n"
        "✅ High-speed direct servers\n"
        "✅ Priority support\n\n"
        "Choose how long to remove ads 👇"
    )
    await call.message.edit_text(msg, reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith('buy_stars_'))
async def send_star_invoice(call: types.CallbackQuery):
    stars = int(call.data.split('_')[2])
    days_map = {50: 30, 105: 90, 350: 365}
    days = days_map.get(stars, 30)

    await bot.send_invoice(
        call.message.chat.id,
        title="TikTok Downloader Premium",
        description=f"Unlock {days} days of ad-free unlimited TikTok downloads.",
        payload=f"premium_{days}_{call.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium ({days} Days)", amount=stars)],
        start_parameter="premium-subscription"
    )

@dp.pre_checkout_query()
async def process_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def handle_successful_payment(message: types.Message):
    u_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    days = int(payload.split('_')[1])
    set_user_attr(u_id, "ad_pass_expiry", int(time.time()) + (days * 86400))
    await message.answer(f"🎉 **Payment Received!**\n\nYour Premium Subscription is active for **{days} days**.", parse_mode="Markdown")

# ----------------------------------------------------
# EXECUTE DOWNLOAD
# ----------------------------------------------------
@dp.callback_query(F.data.startswith('quality_'))
async def handle_download(call: types.CallbackQuery):
    u_id = call.from_user.id
    quality = call.data.replace('quality_', '')
    u_data = get_user_data(u_id)
    url = u_data["tiktok_url"]

    if not url:
        await call.message.edit_text("❌ Session expired. Please send the TikTok link again.")
        return

    await call.message.edit_text("⏳ **Processing your request...**", parse_mode="Markdown")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_URL}?url={url}", timeout=15) as resp:
                data = await resp.json()
                if data.get('success'):
                    result = data.get('result', [{}])[0]
                    download_url = None

                    if quality == 'audio':
                        music_info = result.get('music', {})
                        if isinstance(music_info, dict):
                            download_url = music_info.get('play_url') or music_info.get('url')
                        if not download_url:
                            download_url = result.get('audio')
                    else:
                        videos = result.get('videos', [])
                        if videos:
                            download_url = videos[0].get('url')

                    if download_url:
                        markup = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="/btn_home", style="primary")]
                        ])
                        if quality == 'audio':
                            await call.message.answer_audio(audio=download_url, title="TikTok Audio Stream")
                        else:
                            await call.message.answer_video(video=download_url)
                        await call.message.edit_text("✅ **Download Complete!**", reply_markup=markup, parse_mode="Markdown")
                    else:
                        await call.message.edit_text("❌ Could not extract download link.")
                else:
                    await call.message.edit_text("❌ API Error. Try another link.")
        except Exception:
            await call.message.edit_text("❌ Connection error while downloading.")

async def main():
    print("Bot running with manual check button and native aiogram v3 colors...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
