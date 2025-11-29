import os
import logging
import sqlite3
import secrets
import string
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import BadRequest

# ==================== تنظیمات ====================
TOKEN = "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0"
BOT_USERNAME = "Senderpfilesbot"

# تنظیمات کانال
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
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_key TEXT UNIQUE,
                file_id TEXT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                joined BOOLEAN DEFAULT FALSE,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_requests (
                user_id INTEGER,
                video_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, video_key)
            )
        ''')
        self.conn.commit()
        logging.info("✅ دیتابیس آماده است")
    
    def add_video(self, unique_key, file_id, title=""):
        try:
            self.conn.execute('INSERT INTO videos (unique_key, file_id, title) VALUES (?, ?, ?)', 
                            (unique_key, file_id, title))
            self.conn.commit()
            logging.info(f"✅ ویدیو با کد {unique_key} ذخیره شد")
            return True
        except Exception as e:
            logging.error(f"❌ خطا در ذخیره ویدیو: {e}")
            return False
    
    def get_video(self, unique_key):
        cursor = self.conn.execute('SELECT file_id, title FROM videos WHERE unique_key = ?', (unique_key,))
        result = cursor.fetchone()
        if result:
            return {'file_id': result[0], 'title': result[1]}
        return None
    
    def set_user_joined(self, user_id, username="", first_name=""):
        self.conn.execute(
            'INSERT OR REPLACE INTO users (user_id, joined, username, first_name) VALUES (?, ?, ?, ?)', 
            (user_id, True, username, first_name)
        )
        self.conn.commit()
        logging.info(f"✅ کاربر {user_id} به عنوان عضو ثبت شد")
    
    def has_user_joined(self, user_id):
        cursor = self.conn.execute('SELECT joined FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else False
    
    def add_pending_request(self, user_id, video_key):
        try:
            self.conn.execute(
                'INSERT OR REPLACE INTO pending_requests (user_id, video_key) VALUES (?, ?)',
                (user_id, video_key)
            )
            self.conn.commit()
            return True
        except:
            return False
    
    def get_pending_requests(self, user_id):
        cursor = self.conn.execute('SELECT video_key FROM pending_requests WHERE user_id = ?', (user_id,))
        return [row[0] for row in cursor.fetchall()]
    
    def remove_pending_request(self, user_id, video_key):
        self.conn.execute('DELETE FROM pending_requests WHERE user_id = ? AND video_key = ?', (user_id, video_key))
        self.conn.commit()

db = Database()

# ==================== ابزارهای کمکی ====================
def generate_key():
    return 'vid_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

def create_join_keyboard(video_key=None):
    buttons = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=FORCE_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ تأیید عضویت (روش 1)", callback_data=f"method1_{video_key}" if video_key else "method1")],
        [InlineKeyboardButton("🔍 تأیید عضویت (روش 2)", callback_data=f"method2_{video_key}" if video_key else "method2")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ])

# ==================== روش‌های مختلف بررسی عضویت ====================
async def check_membership_method1(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """روش 1: استفاده مستقیم از get_chat_member"""
    try:
        logging.info(f"🔍 روش 1: بررسی عضویت کاربر {user_id}")
        
        member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL_ID, user_id=user_id)
        status = member.status
        
        logging.info(f"👤 وضعیت کاربر {user_id}: {status}")
        
        if status in ['member', 'administrator', 'creator']:
            logging.info(f"✅ کاربر {user_id} عضو است (روش 1)")
            return True
        
        logging.warning(f"❌ کاربر {user_id} عضو نیست. وضعیت: {status}")
        return False
            
    except BadRequest as e:
        logging.error(f"❌ خطا در روش 1: {e}")
        return False
        
    except Exception as e:
        logging.error(f"❌ خطای غیرمنتظره در روش 1: {e}")
        return False

async def check_membership_method2(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """روش 2: ارسال پیام مخفی و بررسی خطا"""
    try:
        logging.info(f"🔍 روش 2: بررسی عضویت کاربر {user_id}")
        
        # سعی می‌کنیم پیامی در کانال ارسال کنیم (که فقط برای ادمین‌ها ممکن است)
        # اگر کاربر عضو نباشد، خطای "user not participant" می‌گیریم
        test_message = await context.bot.send_message(
            chat_id=FORCE_CHANNEL_ID,
            text=".",  # پیام مخفی
            disable_notification=True
        )
        
        # اگر موفق شد پیام بفرستد، کاربر عضو است
        await context.bot.delete_message(chat_id=FORCE_CHANNEL_ID, message_id=test_message.message_id)
        logging.info(f"✅ کاربر {user_id} عضو است (روش 2)")
        return True
        
    except BadRequest as e:
        error_msg = str(e)
        if "USER_NOT_PARTICIPANT" in error_msg or "user not participant" in error_msg:
            logging.info(f"❌ کاربر {user_id} عضو نیست (روش 2)")
            return False
        else:
            logging.error(f"❌ خطای دیگر در روش 2: {error_msg}")
            return False
            
    except Exception as e:
        logging.error(f"❌ خطای غیرمنتظره در روش 2: {e}")
        return False

async def check_membership_all_methods(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """استفاده از تمام روش‌ها"""
    # روش 1
    result1 = await check_membership_method1(user_id, context)
    if result1:
        return True
    
    # صبر کردن و امتحان روش 2
    await asyncio.sleep(2)
    result2 = await check_membership_method2(user_id, context)
    if result2:
        return True
    
    return False

# ==================== ارسال فایل به کاربر ====================
async def send_video_to_user(context, user_id, video_key, message_to_edit=None):
    try:
        video_data = db.get_video(video_key)
        if not video_data:
            error_text = "❌ فایل مورد نظر پیدا نشد."
            if message_to_edit:
                await message_to_edit.edit_text(error_text)
            else:
                await context.bot.send_message(user_id, error_text)
            return
        
        file_id = video_data['file_id']
        title = video_data['title'] or "فایل شما"
        
        # ارسال فایل
        try:
            await context.bot.send_video(
                user_id, 
                file_id, 
                caption=f"🎬 {title}\n🔑 کد: {video_key}",
                reply_markup=get_main_keyboard()
            )
        except BadRequest:
            await context.bot.send_document(
                user_id,
                file_id,
                caption=f"📁 {title}\n🔑 کد: {video_key}",
                reply_markup=get_main_keyboard()
            )
        
        success_text = "✅ فایل با موفقیت ارسال شد!"
        if message_to_edit:
            await message_to_edit.edit_text(success_text)
        else:
            await context.bot.send_message(user_id, success_text)
        
        # ثبت کاربر به عنوان عضو و حذف درخواست در انتظار
        db.set_user_joined(user_id)
        db.remove_pending_request(user_id, video_key)
        logging.info(f"✅ فایل {video_key} برای کاربر {user_id} ارسال شد")
        
    except Exception as e:
        logging.error(f"❌ خطا در ارسال فایل: {e}")
        error_text = "❌ خطا در ارسال فایل. لطفاً بعداً تلاش کنید."
        if message_to_edit:
            await message_to_edit.edit_text(error_text)
        else:
            await context.bot.send_message(user_id, error_text)

# ==================== هندلر استارت ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    logging.info(f"🚀 کاربر {user_id} دستور /start را اجرا کرد")
    
    # اگر آرگومان دارد (یعنی از لینک آمده)
    if context.args:
        start_arg = context.args[0]
        
        if start_arg.startswith("video_"):
            video_key = start_arg.replace("video_", "")
            logging.info(f"🎬 درخواست فایل {video_key} توسط کاربر {user_id}")
            
            # بررسی وجود فایل
            if not db.get_video(video_key):
                await update.message.reply_text(
                    "❌ لینک معتبر نیست یا فایل حذف شده است.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            # اگر کاربر قبلاً عضو شده
            if db.has_user_joined(user_id):
                logging.info(f"✅ کاربر {user_id} قبلاً عضو شده، ارسال فایل")
                await send_video_to_user(context, user_id, video_key)
                return
            
            # ذخیره درخواست در انتظار
            db.add_pending_request(user_id, video_key)
            
            # نمایش پیام عضویت
            await update.message.reply_text(
                f"🔒 برای دریافت فایل، لطفاً در کانال ما عضو شوید:\n\n"
                f"📢 {CHANNEL_USERNAME}\n\n"
                f"✅ پس از عضویت، یکی از روش‌های زیر را برای تأیید انتخاب کنید:",
                reply_markup=create_join_keyboard(video_key)
            )
    else:
        # پیام خوشامدگویی معمولی
        await update.message.reply_text(
            f"سلام {user.first_name}! 🤖\n\n"
            f"به ربات دریافت فایل خوش آمدید.\n\n"
            f"🎬 برای دریافت فایل روی لینک مخصوص کلیک کنید.\n"
            f"📢 کانال: {CHANNEL_USERNAME}",
            reply_markup=get_main_keyboard()
        )

# ==================== هندلر دکمه ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    logging.info(f"🔘 دکمه {data} توسط کاربر {user_id} فشرده شد")
    
    if data.startswith("method1_") or data.startswith("method2_"):
        video_key = data.split("_", 1)[1] if "_" in data else None
        
        if not video_key:
            # اگر video_key وجود ندارد، از pending_requests بگیر
            pending_requests = db.get_pending_requests(user_id)
            if pending_requests:
                video_key = pending_requests[0]
        
        if not video_key:
            await query.edit_message_text("❌ لینک معتبر نیست.")
            return
        
        # نمایش پیام در حال بررسی
        await query.edit_message_text("🔍 در حال بررسی عضویت... لطفاً صبر کنید.")
        
        # انتخاب روش بررسی
        if data.startswith("method1_"):
            is_member = await check_membership_method1(user_id, context)
            method_name = "روش 1"
        else:
            is_member = await check_membership_method2(user_id, context)
            method_name = "روش 2"
        
        if is_member:
            await query.edit_message_text(f"✅ عضویت شما تأیید شد! ({method_name})\n\nدر حال ارسال فایل...")
            db.set_user_joined(user_id)
            await send_video_to_user(context, user_id, video_key, query.message)
        else:
            await query.edit_message_text(
                f"❌ عضویت شما تأیید نشد. ({method_name})\n\n"
                f"لطفاً مطمئن شوید:\n"
                f"• در کانال {CHANNEL_USERNAME} عضو شده‌اید\n"
                f"• از اکانت درست استفاده می‌کنید\n"
                f"• روش دیگر را امتحان کنید\n\n"
                f"اگر مشکل ادامه دارد، با ادمین تماس بگیرید.",
                reply_markup=create_join_keyboard(video_key)
            )
    
    elif data == "stats":
        await query.edit_message_text(
            f"📊 آمار ربات:\n\n"
            f"🤖 وضعیت: فعال\n"
            f"🔗 کانال: {CHANNEL_USERNAME}\n"
            f"👤 برای دریافت فایل از لینک استفاده کنید",
            reply_markup=get_main_keyboard()
        )
    
    elif data == "help":
        await query.edit_message_text(
            "📖 راهنمای ربات:\n\n"
            "🎬 روش دریافت فایل:\n"
            "1. روی لینک مخصوص فایل کلیک کنید\n"
            "2. در کانال عضو شوید\n"
            "3. روی یکی از دکمه‌های تأیید کلیک کنید\n"
            "4. فایل دریافت می‌شود\n\n"
            f"📢 کانال: {CHANNEL_USERNAME}",
            reply_markup=get_main_keyboard()
        )

# ==================== هندلر آپلود فایل در کانال ====================
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return
    
    message = update.channel_post
    file_id = None
    file_type = None
    title = ""
    
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
        title = message.caption or "ویدیو"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        title = message.caption or message.document.file_name or "فایل"
    else:
        return
    
    unique_key = generate_key()
    
    if db.add_video(unique_key, file_id, title):
        link = f"https://t.me/{BOT_USERNAME}?start=video_{unique_key}"
        
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"📦 فایل جدید ذخیره شد!\n\n"
                f"📁 نوع: {file_type}\n"
                f"🔑 کد: {unique_key}\n"
                f"📝 عنوان: {title}\n"
                f"🔗 لینک:\n{link}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📬 اشتراک‌گذاری لینک", url=link)
                ]])
            )
            logging.info(f"✅ فایل جدید با کد {unique_key} ذخیره شد")
        except Exception as e:
            logging.error(f"❌ خطا در ارسال به ادمین: {e}")

# ==================== دستورات ادمین ====================
async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این دستور فقط برای ادمین است.")
        return
    
    # تست هر دو روش
    result1 = await check_membership_method1(user_id, context)
    result2 = await check_membership_method2(user_id, context)
    
    await update.message.reply_text(
        f"🔍 تست عضویت:\n\n"
        f"👤 کاربر: {user_id}\n"
        f"📢 کانال ID: {FORCE_CHANNEL_ID}\n"
        f"🔗 لینک: {FORCE_CHANNEL_LINK}\n\n"
        f"✅ روش 1 (get_chat_member): {result1}\n"
        f"✅ روش 2 (send_message): {result2}\n\n"
        f"💡 اگر هر دو False هستند:\n"
        f"• مطمئن شوید ربات در کانال ادمین است\n"
        f"• مطمئن شوید شما در کانال عضو هستید"
    )

async def manual_approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور برای تأیید دستی کاربر"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("لطفاً ID کاربر را وارد کنید: /approve <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        db.set_user_joined(target_user_id)
        
        # ارسال تمام فایل‌های در انتظار
        pending_requests = db.get_pending_requests(target_user_id)
        for video_key in pending_requests:
            await send_video_to_user(context, target_user_id, video_key)
        
        await update.message.reply_text(f"✅ کاربر {target_user_id} تأیید شد و فایل‌ها ارسال شدند.")
        
    except ValueError:
        await update.message.reply_text("❌ ID کاربر نامعتبر است.")

# ==================== اجرای ربات ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    logging.info("🚀 شروع ربات...")
    logging.info(f"📢 کانال ID: {FORCE_CHANNEL_ID}")
    logging.info(f"🔗 لینک کانال: {FORCE_CHANNEL_LINK}")
    
    app = Application.builder().token(TOKEN).build()
    
    # هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CommandHandler("approve", manual_approve_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # هندلر پست‌های کانال
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL), 
        handle_channel_post
    ))
    
    logging.info("✅ ربات آماده است")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
