import logging
import sqlite3
import secrets
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import BadRequest, Forbidden

# ==================== تنظیمات ====================
TOKEN = "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0"
BOT_USERNAME = "Senderpfilesbot"          # بدون @
FORCE_CHANNEL_ID = -1002034901903
CHANNEL_LINK = "https://t.me/betdesignernet"
ADMIN_ID = 7321524568

logging.basicConfig(level=logging.INFO)

# ==================== دیتابیس ساده ====================
db = sqlite3.connect("bot.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS files (key TEXT PRIMARY KEY, file_id TEXT, title TEXT)")
db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined INTEGER DEFAULT 0)")
db.execute("CREATE TABLE IF NOT EXISTS pending (user_id INTEGER, key TEXT, PRIMARY KEY(user_id, key))")
db.commit()

def add_file(key, file_id, title=""):
    db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (key, file_id, title))
    db.commit()

def get_file(key):
    cur = db.execute("SELECT file_id, title FROM files WHERE key=?", (key,))
    row = cur.fetchone()
    return {"file_id": row[0], "title": row[1]} if row else None

def user_joined(user_id):
    db.execute("INSERT OR REPLACE INTO users VALUES (?, 1)", (user_id,))
    db.commit()

def is_joined(user_id):
    cur = db.execute("SELECT joined FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row and row[0] == 1

def add_pending(user_id, key):
    db.execute("INSERT OR IGNORE INTO pending VALUES (?, ?)", (user_id, key))
    db.commit()

def remove_pending(user_id, key):
    db.execute("DELETE FROM pending WHERE user_id=? AND key=?", (user_id, key))
    db.commit()

def get_pending(user_id):
    cur = db.execute("SELECT key FROM pending WHERE user_id=?", (user_id,))
    return [row[0] for row in cur.fetchall()]

# ==================== کیبوردها ====================
def join_kb(key=""):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("عضویت در کانال", url=CHANNEL_LINK),
        InlineKeyboardButton("تأیید عضویت", callback_data=f"check_{key}")
    ]])

def main_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("آمار", callback_data="stats"),
        InlineKeyboardButton("راهنما", callback_data="help")
    ]])

# ==================== بررسی عضویت (درست و قطعی) ====================
async def check_member(user_id):
    try:
        member = await app.bot.get_chat_member(FORCE_CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except BadRequest as e:
        if "not found" in str(e):
            return False
    except Forbidden:
        logging.error("ربات از کانال بن شده یا دسترسی نداره!")
        return False
    except Exception as e:
        logging.error(f"خطا در چک عضویت: {e}")
    return False

# ==================== هندلرها ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("vid_"):
        key = args[0]

        if not get_file(key):
            await update.message.reply_text("فایل پیدا نشد یا حذف شده.", reply_markup=main_kb())
            return

        if is_joined(user.id):
            await send_file(context, user.id, key)
            return

        add_pending(user.id, key)
        await update.message.reply_text(
            "برای دریافت فایل باید عضو کانال بشید:\n\n"
            f"کانال: {CHANNEL_LINK}\n\n"
            "بعد از عضویت روی «تأیید عضویت» بزنید",
            reply_markup=join_kb(key)
        )
    else:
        await update.message.reply_text(
            f"سلام {user.first_name}!\n\n"
            "لینک فایل رو برام بفرست تا فایل رو بگیری\n"
            f"کانال: {CHANNEL_LINK}",
            reply_markup=main_kb()
        )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    data = q.data

    if data.startswith("check_"):
        key = data[6:] or get_pending(user_id)[0] if get_pending(user_id) else None
        if not key or not get_file(key):
            await q.edit_message_text("لینک اشتباهه")
            return

        await q.edit_message_text("در حال چک کردن عضویت...")

        if await check_member(user_id):
            await q.edit_message_text("عضویت تأیید شد! در حال ارسال فایل...")
            user_joined(user_id)
            remove_pending(user_id, key)
            await send_file(context, user_id, key)
        else:
            await q.edit_message_text(
                "هنوز عضو کانال نیستی!\n\n"
                "اول برو عضو کانال شو، بعد دوباره بزن «تأیید عضویت»",
                reply_markup=join_kb(key)
            )

    elif data == "stats":
        await q.edit_message_text("ربات فعاله", reply_markup=main_kb())
    elif data == "help":
        await q.edit_message_text("روی لینک فایل بزن → عضو کانال شو → تأیید عضویت → فایل میاد", reply_markup=main_kb())

async def send_file(context, user_id, key):
    data = get_file(key)
    caption = f"{data['title']}\nکد: {key}\nکانال: {CHANNEL_LINK}"

    try:
        await context.bot.send_video(user_id, data["file_id"], caption=caption, reply_markup=main_kb())
    except:
        await context.bot.send_document(user_id, data["file_id"], caption=caption, reply_markup=main_kb())
    await context.bot.send_message(user_id, "فایل ارسال شد!")

# ==================== وقتی تو کانال فایل آپلود میشه ====================
async def channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if msg.chat.id != FORCE_CHANNEL_ID:
        return

    file_id = None
    title = "فایل"

    if msg.video:
        file_id = msg.video.file_id
        title = msg.caption or "ویدیو"
    elif msg.document:
        file_id = msg.document.file_id
        title = msg.caption or msg.document.file_name or "داکیومنت"

    if file_id:
        key = "vid_" + secrets.token_hex(5)
        add_file(key, file_id, title)
        link = f"https://t.me/{BOT_USERNAME}?start={key}"
        await context.bot.send_message(
            ADMIN_ID,
            f"فایل جدید!\n\nعنوان: {title}\nلینک:\n{link}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("اشتراک لینک", url=link)]])
        )

# ==================== اجرا ====================
app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.CHAT_TYPE_CHANNEL & (filters.VIDEO | filters.DOCUMENT), channel_handler))

print("ربات روشن شد...")
app.run_polling(drop_pending_updates=True)
