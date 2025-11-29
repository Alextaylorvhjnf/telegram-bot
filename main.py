# main.py - نسخه کامل و به‌روز شده برای python-telegram-bot v21.6+
import os
import logging
import sqlite3
import re
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest

# ==================== تنظیمات ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Senderpfilesbot").lstrip("@")
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "@betdesignernet")
PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "-1002920455639"))
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "7321524568").split(",") if x.strip()]

# ==================== دیتابیس ====================
class Database:
    def __init__(self, db_path="films_bot.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS films (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    film_code TEXT UNIQUE NOT NULL,
                    file_id TEXT NOT NULL,
                    title TEXT,
                    caption TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id INTEGER PRIMARY KEY,
                    pending_film_code TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        logging.info("دیتابیس آماده است")

    def add_film(self, film_code, file_id, title=None, caption=None):
        with self.get_connection() as conn:
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO films (film_code, file_id, title, caption)
                    VALUES (?, ?, ?, ?)
                ''', (film_code, file_id, title, caption))
                return True
            except Exception as e:
                logging.error(f"خطا در ذخیره فیلم: {e}")
                return False

    def get_film(self, film_code):
        with self.get_connection() as conn:
            cur = conn.execute('SELECT film_code, file_id, title, caption FROM films WHERE film_code = ?', (film_code,))
            row = cur.fetchone()
            if row:
                return {'film_code': row[0], 'file_id': row[1], 'title': row[2], 'caption': row[3]}
            return None

    def get_all_films(self):
        with self.get_connection() as conn:
            cur = conn.execute('SELECT film_code, title FROM films ORDER BY added_at DESC')
            return [{'film_code': r[0], 'title': r[1] or r[0]} for r in cur.fetchall()]

    def get_all_films_detailed(self):
        with self.get_connection() as conn:
            cur = conn.execute('SELECT film_code, title, file_id, added_at FROM films ORDER BY added_at DESC')
            return [{'film_code': r[0], 'title': r[1], 'file_id': r[2], 'added_at': r[3]} for r in cur.fetchall()]

    def add_user(self, user_id, username, first_name, last_name):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))

    def get_users_count(self):
        with self.get_connection() as conn:
            return conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    def get_films_count(self):
        with self.get_connection() as conn:
            return conn.execute('SELECT COUNT(*) FROM films').fetchone()[0]

    def set_pending_film(self, user_id, film_code):
        with self.get_connection() as conn:
            conn.execute('INSERT OR REPLACE INTO user_sessions (user_id, pending_film_code) VALUES (?, ?)',
                         (user_id, film_code))

    def get_pending_film(self, user_id):
        with self.get_connection() as conn:
            row = conn.execute('SELECT pending_film_code FROM user_sessions WHERE user_id = ?', (user_id,)).fetchone()
            return row[0] if row else None

    def clear_pending_film(self, user_id):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))

db = Database()

# ==================== کیبوردها ====================
def create_start_link(code):
    return f"https://t.me/{BOT_USERNAME}?start={code}"

def get_join_keyboard(code=None):
    url = f"https://t.me/{FORCE_SUB_CHANNEL.lstrip('@')}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("عضویت در کانال", url=url)],
        [InlineKeyboardButton("عضو شدم", callback_data=f"check_join_{code}" if code else "check_join")]
    ])

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("راهنما", callback_data="help")],
        [InlineKeyboardButton("لیست فیلم‌ها", callback_data="list_films")]
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("آمار ربات", callback_data="admin_stats")],
        [InlineKeyboardButton("مدیریت فیلم‌ها", callback_data="admin_films")],
        [InlineKeyboardButton("مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("بازگشت", callback_data="back_to_main")]
    ])

# ==================== چک عضویت ====================
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ("member", "administrator", "creator")
    except BadRequest:
        return False
    except Exception as e:
        logging.error(f"خطا در چک عضویت: {e}")
        return False

# ==================== هندلر پست کانال خصوصی ====================
async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post.chat_id != PRIVATE_CHANNEL_ID:
        return
    msg = update.channel_post
    if not (msg.video or msg.document):
        return

    file_id = msg.video.file_id if msg.video else msg.document.file_id
    caption = msg.caption or ""

    match = re.search(r'film\d+', caption, re.IGNORECASE)
    if not match:
        logging.warning("کد فیلم در کپشن پیدا نشد")
        return

    film_code = match.group().lower()
    title = caption.split("\n")[0] if "\n" in caption else caption[:100]

    if db.add_film(film_code, file_id, title, caption):
        logging.info(f"فیلم {film_code} ذخیره شد")
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"فیلم جدید ذخیره شد\n\nکد: `{film_code}`\nعنوان: {title}",
                    parse_mode="Markdown"
                )
            except:
                pass

# ==================== ارسال فیلم به کاربر ====================
async def send_film(update: Update, context: ContextTypes.DEFAULT_TYPE, film_code: str, user_id: int):
    if not await check_membership(user_id, context):
        db.set_pending_film(user_id, film_code)
        text = f"برای دریافت فیلم باید در کانال عضو شوید:\n{FORCE_SUB_CHANNEL}"
        kb = get_join_keyboard(film_code)
        if update.message:
            await update.message.reply_text(text, reply_markup=kb)
        else:
            await update.callback_query.edit_message_text(text, reply_markup=kb)
        return

    film = db.get_film(film_code)
    if not film:
        await (update.message or update.callback_query.message).reply_text("فیلم مورد نظر یافت نشد.")
        return

    caption = film['caption'] or film['title'] or f"فیلم {film_code}"
    try:
        if film['file_id'].startswith(('BA', 'Ag')):  # video file_id
            await context.bot.send_video(user_id, film['file_id'], caption=caption, reply_markup=get_main_keyboard())
        else:
            await context.bot.send_document(user_id, film['file_id'], caption=caption, reply_markup=get_main_keyboard())

        if update.callback_query:
            await update.callback_query.edit_message_text("فیلم با موفقیت ارسال شد!")
        db.clear_pending_film(user_id)
        logging.info(f"کاربر {user_id} فیلم {film_code} را دریافت کرد")
    except Exception as e:
        logging.error(f"خطا در ارسال فیلم: {e}")
        await (update.message or update.callback_query.message).reply_text("خطا در ارسال فیلم. دوباره تلاش کنید.")

# ==================== /start ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)

    if user.id in ADMIN_IDS:
        if context.args:
            await send_film(update, context, context.args[0], user.id)
            return
        await update.message.reply_text(
            f"سلام ادمین {user.first_name}!\nبه پنل مدیریت خوش آمدید.",
            reply_markup=get_admin_keyboard()
        )
        return

    # کاربر عادی
    if context.args:
        await send_film(update, context, context.args[0], user.id)
    else:
        await update.message.reply_text(
            f"سلام {user.first_name}!\nبه ربات دریافت فیلم خوش آمدید\nحتما در کانال عضو شوید:\n{FORCE_SUB_CHANNEL}",
            reply_markup=get_main_keyboard()
        )

# ==================== دکمه‌ها ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # عضویت چک کردن
    if data.startswith("check_join"):
        code = data[len("check_join_"):] if "_" in data else None
        if not code:
            code = db.get_pending_film(user_id)

        if await check_membership(user_id, context):
            if code:
                await send_film(update, context, code, user_id)
            else:
                await query.edit_message_text("عالی! حالا می‌تونید از ربات استفاده کنید", reply_markup=get_main_keyboard())
        else:
            await query.edit_message_text("هنوز عضو کانال نشدید!", reply_markup=get_join_keyboard(code))
        return

    # لیست فیلم‌ها
    if data == "list_films":
        films = db.get_all_films()
        if not films:
            await query.edit_message_text("در حال حاضر فیلمی موجود نیست.", reply_markup=get_main_keyboard())
            return
        text = "لیست فیلم‌های موجود:\n\n"
        kb = []
        for f in films[:15]:
            text += f"• {f['title']}\n"
            kb.append([InlineKeyboardButton(f['title'], url=create_start_link(f['film_code']))])
        kb.append([InlineKeyboardButton("بازگشت", callback_data="back_to_main")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        return

    # راهنما
    if data == "help":
        help_text = f"""
راهنمای ربات:
1. روی لینک مخصوص فیلم کلیک کنید
2. اگر لینک کار نکرد → عضو کانال شوید
3. دکمه «عضو شدم» را بزنید
4. فیلم برای شما ارسال می‌شود

نمونه لینک:
https://t.me/{BOT_USERNAME}?start=film001

کانال: {FORCE_SUB_CHANNEL}
        """
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بازگشت", callback_data="back_to_main")]
        ]))
        return

    # بازگشت به منوی اصلی
    if data == "back_to_main":
        if user_id in ADMIN_IDS:
            await query.edit_message_text("به پنل مدیریت بازگشتید", reply_markup=get_admin_keyboard())
        else:
            await query.edit_message_text("به ربات خوش آمدید!", reply_markup=get_main_keyboard())
        return

    # آمار ادمین
    if data == "admin_stats":
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("دسترسی ممنوع.")
            return
        text = f"""
آمار ربات:
تعداد فیلم‌ها: {db.get_films_count()}
تعداد کاربران: {db.get_users_count()}
تعداد ادمین‌ها: {len(ADMIN_IDS)}
وضعیت: فعال
        """
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بازگشت", callback_data="back_to_main")]
        ]))
        return

    # مدیریت فیلم‌ها
    if data == "admin_films":
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("دسترسی ممنوع.")
            return
        films = db.get_all_films_detailed()
        if not films:
            await query.edit_message_text("هیچ فیلمی وجود ندارد.")
            return
        text = "لیست فیلم‌ها:\n\n"
        for i, f in enumerate(films[:10], 1):
            text += f"{i}. {f['title']}\nکد: {f['film_code']}\nتاریخ: {f['added_at'][:16]}\n\n"
        if len(films) > 10:
            text += f"\nو {len(films)-10} فیلم دیگر..."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بازگشت", callback_data="back_to_main")]
        ]))
        return

    # مدیریت کاربران
    if data == "admin_users":
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("دسترسی ممنوع.")
            return
        await query.edit_message_text(
            f"تعداد کاربران: {db.get_users_count()}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_to_main")]])
        )
        return

# ==================== دستورات ادمین ====================
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("دسترسی ممنوع.")
        return
    await update.message.reply_text(f"""
آمار کامل:
فیلم‌ها: {db.get_films_count()}
کاربران: {db.get_users_count()}
    """)

async def films_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("دسترسی ممنوع.")
        return
    films = db.get_all_films_detailed()
    text = "لیست کامل فیلم‌ها:\n\n" if films else "هیچ فیلمی نیست."
    for i, f in enumerate(films, 1):
        text += f"{i}. {f['title']}\nکد: {f['film_code']}\nتاریخ: {f['added_at'][:16]}\n\n"
    if len(text) > 4000:
        text = text[:3900] + "\n... (ادامه در لاگ)"
    await update.message.reply_text(text)

# ==================== main ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.info("ربات در حال راه‌اندازی...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("films", films_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(
        filters.Chat(PRIVATE_CHANNEL_ID) & (filters.VIDEO | filters.DOCUMENT),
        channel_post_handler
    ))

    logging.info("ربات با موفقیت راه‌اندازی شد!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
