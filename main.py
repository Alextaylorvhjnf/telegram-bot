import os
import logging
import sqlite3
import secrets
import string
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import BadRequest, Forbidden

# ==================== تنظیمات ====================
TOKEN = "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0"
BOT_USERNAME = "Senderpfilesbot"

FORCE_CHANNEL_ID = -1002034901903
FORCE_CHANNEL_LINK = "https://t.me/betdesignernet/132"
CHANNEL_USERNAME = "@betdesignernet"
ADMIN_ID = 7321524568

# ==================== دیتابیس ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.init_db()

    def init_db(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_key TEXT UNIQUE,
                file_id TEXT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                joined BOOLEAN DEFAULT 0,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS pending_requests (
                user_id INTEGER,
                video_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, video_key)
            );
        ''')
        self.conn.commit()
        logging.info("دیتابیس آماده است")

    def add_video(self, unique_key, file_id, title=""):
        try:
            self.conn.execute('INSERT OR IGNORE INTO videos (unique_key, file_id, title) VALUES (?, ?, ?)',
                            (unique_key, file_id, title))
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"خطا در ذخیره ویدیو: {e}")
            return False

    def get_video(self, unique_key):
        cur = self.conn.execute('SELECT file_id, title FROM videos WHERE unique_key = ?', (unique_key,))
        row = cur.fetchone()
        return {'file_id': row[0], 'title': row[1]} if row else None

    def set_user_joined(self, user_id, username="", first_name=""):
        self.conn.execute('INSERT OR REPLACE INTO users (user_id, joined, username, first_name) VALUES (?, 1, ?, ?)',
                         (user_id, username, first_name))
        self.conn.commit()

    def is_user_joined(self, user_id):
        cur = self.conn.execute('SELECT joined FROM users WHERE user_id = ?', (user_id,))
        row = cur.fetchone()
        return bool(row[0]) if row else False

    def add_pending(self, user_id, video_key):
        self.conn.execute('INSERT OR IGNORE INTO pending_requests (user_id, video_key) VALUES (?, ?)',
                         (user_id, video_key))
        self.conn.commit()

    def get_pending(self, user_id):
        cur = self.conn.execute('SELECT video_key FROM pending_requests WHERE user_id = ?', (user_id,))
        return [row[0] for row in cur.fetchall()]

    def remove_pending(self, user_id, video_key):
        self.conn.execute('DELETE FROM pending_requests WHERE user_id = ? AND video_key = ?', (user_id, video_key))
        self.conn.commit()

db = Database()

# ==================== ابزارها ====================
def generate_key():
    return 'vid_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))

def join_keyboard(video_key=None):
    key = video_key or ""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("عضویت در کانال", url=FORCE_CHANNEL_LINK),
    ], [
        InlineKeyboardButton("تأیید عضویت", callback_data=f"check_{key}")
    ]])

def main_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("آمار", callback_data="stats"),
        InlineKeyboardButton("راهنما", callback_data="help")
    ]])

# ==================== بررسی عضویت (فقط روش درست) ====================
async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL_ID, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except BadRequest as e:
        if "user not found" in str(e).lower():
            return False
        logging.error(f"BadRequest چک عضویت: {e}")
        return False
    except Forbidden:
        logging.error("ربات از کانال بن شده یا دسترسی نداره")
        return False
    except Exception as e:
        logging.error(f"خطا در چک عضویت: {e}")
        return False

# ==================== ارسال فایل ====================
async def send_file(context: ContextTypes.DEFAULT_TYPE, user_id: int, video_key: str, msg_to_edit=None):
    data = db.get_video(video_key)
    if not data:
        text = "فایل پیدا نشد یا حذف شده."
        if msg_to_edit:
            await msg_to_edit.edit_text(text)
        else:
            await context.bot.send_message(user_id, text)
        return

    caption = f"عنوان: {data['title'] or 'فایل'}\nکد: {video_key}\nکانال: {CHANNEL_USERNAME}"

    try:
        await context.bot.send_video(user_id, data['file_id'], caption=caption, reply_markup=main_keyboard())
    except BadRequest:
        try:
            await context.bot.send_document(user_id, data['file_id'], caption=caption, reply_markup=main_keyboard())
        except Exception as e2:
            logging.error(f"ارسال ویدیو/داکیومنت ناموفق: {e2}")
            await context.bot.send_message(user_id, "خطا در ارسال فایل.")

    success = "فایل با موفقیت ارسال شد!"
    if msg_to_edit:
        await msg_to_edit.edit_text(success)
    else:
        await context.bot.send_message(user_id, success)

    db.set_user_joined(user_id)
    db.remove_pending(user_id, video_key)

# ==================== هندلرها ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("video_"):
        key = args[0].replace("video_", "", 1)
        if not db.get_video(key):
            await update.message.reply_text("لینک نامعتبر یا فایل حذف شده.", reply_markup=main_keyboard())
            return

        if db.is_user_joined(user.id):
            await send_file(context, user.id, key)
            return

        db.add_pending(user.id, key)
        await update.message.reply_text(
            f"برای دریافت فایل باید در کانال عضو شوید:\n\n"
            f"کانال: {CHANNEL_USERNAME}\n\n"
            f"بعد از عضویت روی دکمه زیر بزنید:",
            reply_markup=join_keyboard(key)
        )
    else:
        await update.message.reply_text(
            f"سلام {user.first_name}!\n\n"
            f"به ربات دانلود فایل خوش آمدید\n"
            f"لینک مخصوص فایل رو بزنید تا فایل رو دریافت کنید\n"
            f"کانال: {CHANNEL_USERNAME}",
            reply_markup=main_keyboard()
        )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("check_"):
        key = data[6:] if data[6:] else None
        if not key:
            pending = db.get_pending(user_id)
            key = pending[0] if pending else None
        if not key or not db.get_video(key):
            await query.edit_message_text("لینک نامعتبر.")
            return

        await query.edit_message_text("در حال بررسی عضویت...")

        if await is_member(user_id, context):
            await query.edit_message_text("عضویت تأیید شد! در حال ارسال فایل...")
            await send_file(context, user_id, key, query.message)
        else:
            await query.edit_message_text(
                "هنوز عضو کانال نیستید!\n\n"
                f"لطفاً در {CHANNEL_USERNAME} عضو شوید و دوباره امتحان کنید.",
                reply_markup=join_keyboard(key)
            )

    elif data == "stats":
        await query.edit_message_text("ربات فعاله\nبرای دریافت فایل از لینک استفاده کنید", reply_markup=main_keyboard())
    elif data == "help":
        await query.edit_message_text(
            "راهنما:\n"
            "1. روی لینک فایل کلیک کنید\n"
            "2. در کانال عضو شوید\n"
            "3. روی «تأیید عضویت» بزنید\n"
            "4. فایل دریافت میشه",
            reply_markup=main_keyboard()
        )

# ==================== دریافت فایل از کانال ====================
async def channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat.id != FORCE_CHANNEL_ID:
        return

    file_id = None
    title = "فایل"

    if msg.video:
        file_id = msg.video.file_id
        title = msg.caption or "ویدیو"
    elif msg.document:
        file_id = msg.document.file_id
        title = msg.caption or msg.document.file_name or "داکیومنت"

    if not file_id:
        return

    key = generate_key()
    if db.add_video(key, file_id, title):
        link = f"https://t.me/{BOT_USERNAME}?start=video_{key}"
        await context.bot.send_message(
            ADMIN_ID,
            f"فایل جدید ذخیره شد!\n\n"
            f"عنوان: {title}\n"
            f"کد: {key}\n"
            f"لینک: {link}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("اشتراک لینک", url=link)]])
        )

# ==================== دستورات ادمین ====================
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    res = await is_member(update.effective_user.id, context)
    await update.message.reply_text(f"نتیجه چک عضویت شما: {'عضو هستید' if res else 'عضو نیستید'}")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.args:
        return
    try:
        uid = int(context.args[0])
        db.set_user_joined(uid)
        for key in db.get_pending(uid):
            await send_file(context, uid, key)
        await update.message.reply_text(f"کاربر {uid} دستی تأیید شد.")
    except:
        await update.message.reply_text("آیدی اشتباهه")

# ==================== اجرا ====================
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("ربات در حال شروع...")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL), channel_post))

    logging.info("ربات آماده و در حال اجراست!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
