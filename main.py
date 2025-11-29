# main.py - نسخه نهایی و کاملاً کارکردی (2025)
import os
import logging
import sqlite3
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import BadRequest

# ==================== تنظیمات ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Senderpfilesbot").lstrip("@")
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "@betdesignernet")
PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "-1002920455639"))
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "7321524568").split(",") if x.strip()]

# ==================== دیتابیس ====================
class DB:
    def __init__(self):
        self.conn = sqlite3.connect("bot.db", check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS films (
                code TEXT PRIMARY KEY,
                file_id TEXT,
                title TEXT,
                caption TEXT
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS pending (
                user_id INTEGER PRIMARY KEY,
                film_code TEXT
            )
        ''')
        self.conn.commit()

    def add_film(self, code, file_id, title="", caption=""):
        self.conn.execute("INSERT OR REPLACE INTO films VALUES (?, ?, ?, ?)", (code.lower(), file_id, title, caption))
        self.conn.commit()

    def get_film(self, code):
        cur = self.conn.execute("SELECT file_id, title, caption FROM films WHERE code = ?", (code.lower(),))
        row = cur.fetchone()
        return {"file_id": row[0], "title": row[1], "caption": row[2]} if row else None

    def set_pending(self, user_id, code):
        self.conn.execute("INSERT OR REPLACE INTO pending VALUES (?, ?)", (user_id, code.lower()))
        self.conn.commit()

    def get_pending(self, user_id):
        cur = self.conn.execute("SELECT film_code FROM pending WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None

    def clear_pending(self, user_id):
        self.conn.execute("DELETE FROM pending WHERE user_id = ?", (user_id,))
        self.conn.commit()

db = DB()

# ==================== کیبوردها ====================
def link(code): return f"https://t.me/{BOT_USERNAME}?start={code}"

def join_kb(code=None):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{FORCE_SUB_CHANNEL.lstrip('@')}"),
        InlineKeyboardButton("عضو شدم", callback_data=f"check_{code}" if code else "check")
    ]])

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("راهنما", callback_data="help")],
        [InlineKeyboardButton("لیست فیلم‌ها", callback_data="list")]
    ])

# ==================== چک عضویت ====================
async def is_member(user_id, context):
    try:
        chat_member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except:
        return False

# ==================== ارسال فیلم ====================
async def send_film(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str, user_id: int):
    if not await is_member(user_id, context):
        db.set_pending(user_id, code)
        text = f"برای دریافت فیلم، اول باید در کانال عضو بشی:\n{FORCE_SUB_CHANNEL}"
        kb = join_kb(code)
        if update.message:
            await update.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)
        else:
            await update.callback_query.edit_message_text(text, reply_markup=kb, disable_web_page_preview=True)
        return

    film = db.get_film(code)
    if not film:
        await (update.message or update.callback_query.message).reply_text("فیلم پیدا نشد یا حذف شده.")
        return

    caption = film.get("caption") or film.get("title") or f"فیلم {code.upper()}"
    try:
        if film["file_id"].startswith(("BA", "Ag")):  # ویدیو
            await context.bot.send_video(user_id, film["file_id"], caption=caption, reply_markup=main_kb())
        else:
            await context.bot.send_document(user_id, film["file_id"], caption=caption, reply_markup=main_kb())

        success_text = f"فیلم {code.upper()} برات ارسال شد"
        if update.callback_query:
            await update.callback_query.edit_message_text(success_text)
        db.clear_pending(user_id)
    except Exception as e:
        logging.error(f"خطا ارسال: {e}")
        await (update.message or update.callback_query.message).reply_text("خطا در ارسال. دوباره امتحان کن.")

# ==================== هندلرهای اصلی ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if user_id in ADMIN_IDS and args:
        return await send_film(update, context, args[0], user_id)

    if args:
        return await send_film(update, context, args[0], user_id)

    await update.message.reply_text(
        f"سلام {update.effective_user.first_name}!\nبه ربات دانلود فیلم خوش اومدی\n\n"
        f"کانال ما: {FORCE_SUB_CHANNEL}\n"
        "لینک فیلم رو برات بفرستم بفرست!",
        reply_markup=main_kb()
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    user_id = q.from_user.id

    # دکمه "عضو شدم"
    if data.startswith("check"):
        code = data[6:] if len(data) > 5 else db.get_pending(user_id)  # check_film123 → film123

        if await is_member(user_id, context):
            if code:
                await send_film(update, context, code, user_id)
            else:
                await q.edit_message_text("عالی! حالا لینک فیلم رو بفرست", reply_markup=main_kb())
        else:
            await q.edit_message_text("هنوز عضو نشدی!\nاول عضو شو بعد دوباره بزن «عضو شدم»", reply_markup=join_kb(code or ""))

    # لیست فیلم‌ها
    elif data == "list":
        cur = db.conn.execute("SELECT code, title FROM films ORDER BY rowid DESC LIMIT 20")
        if not cur.fetchall():
            await q.edit_message_text("هنوز فیلمی اضافه نشده.")
            return
        text = "لیست فیلم‌ها:\n\n"
        kb = []
        for code, title in cur:
            title = title or code.upper()
            text += f"• {title}\n"
            kb.append([InlineKeyboardButton(title, url=link(code))])
        kb.append([InlineKeyboardButton("بازگشت", callback_data="back")])
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

    elif data == "help":
        await q.edit_message_text(
            "راهنما:\n\n"
            "1. روی لینک فیلم کلیک کن\n"
            "2. اگر گفت عضو شو → عضو کانال شو\n"
            "3. روی «عضو شدم» بزن\n"
            "4. فیلم برات میاد!\n\n"
            f"کانال: {FORCE_SUB_CHANNEL}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back")]])
        )

    elif data == "back":
        await q.edit_message_text("به منوی اصلی برگشتی", reply_markup=main_kb())

# ==================== دریافت فیلم از کانال خصوصی ====================
async def channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if msg.chat.id != PRIVATE_CHANNEL:
        return
    if not (msg.video or msg.document):
        return

    file_id = msg.video.file_id if msg.video else msg.document.file_id
    caption = msg.caption or ""

    match = re.search(r'film\d+', caption, re.I)
    if not match:
        return

    code = match.group().lower()
    title = caption.split("\n")[0][:100] if caption else "فیلم"

    db.add_film(code, file_id, title, caption)

    for admin in ADMIN_IDS:
        try:
            await context.bot.send_message(admin, f"فیلم جدید اضافه شد:\n{code.upper()}\n{title}")
        except:
            pass

# ==================== main ====================
def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.Chat(PRIVATE_CHANNEL) & (filters.VIDEO | filters.DOCUMENT), channel_post))

    logging.info("ربات با موفقیت راه‌اندازی شد!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
