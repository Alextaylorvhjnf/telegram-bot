import os
import logging
import sqlite3
import secrets
import string
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import BadRequest

# ==================== تنظیمات ====================
TOKEN = "8519774430:AAGHPewxXjkmj3fMmjjtMMlb3GD2oXGFR-0"
BOT_USERNAME = "Senderpfilesbot"

# 🔥 تنظیمات کانال
FORCE_CHANNEL_ID = -1002034901903  # ID عددی کانال
FORCE_CHANNEL_LINK = "https://t.me/betdesignernet/132"  # لینک مستقیم کانال
CHANNEL_USERNAME = "@betdesignernet"  # یوزرنیم کانال

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

db = Database()

# ==================== ابزارهای کمکی ====================
def generate_key():
    return 'vid_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

def create_join_keyboard(video_key=None):
    """ایجاد کیبورد برای عضویت"""
    buttons = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=FORCE_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ بررسی عضویت", callback_data=f"check_{video_key}" if video_key else "check")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_main_keyboard():
    """کیبورد اصلی"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ])

# ==================== بررسی عضویت ====================
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    بررسی عضویت کاربر در کانال با ID عددی
    """
    try:
        logging.info(f"🔍 بررسی عضویت کاربر {user_id} در کانال {FORCE_CHANNEL_ID}")
        
        member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL_ID, user_id=user_id)
        status = member.status
        
        logging.info(f"👤 وضعیت کاربر {user_id}: {status}")
        
        if status in ['member', 'administrator', 'creator']:
            logging.info(f"✅ کاربر {user_id} عضو کانال است")
            return True
        else:
            logging.warning(f"❌ کاربر {user_id} عضو نیست. وضعیت: {status}")
            return False
            
    except BadRequest as e:
        error_msg = str(e)
        logging.error(f"❌ خطا در بررسی عضویت: {error_msg}")
        
        if "Chat not found" in error_msg:
            logging.error("❌ کانال پیدا نشد! مطمئن شوید:")
            logging.error(f"   1. ID کانال صحیح است: {FORCE_CHANNEL_ID}")
            logging.error("   2. ربات در کانال ادمین است")
        elif "bot is not a member" in error_msg:
            logging.error("❌ ربات عضو کانال نیست! ربات را به کانال اضافه کنید")
        
        return False
        
    except Exception as e:
        logging.error(f"❌ خطای غیرمنتظره در بررسی عضویت: {e}")
        return False

# ==================== ارسال فایل به کاربر ====================
async def send_video_to_user(context, user_id, video_key, message_to_edit=None):
    """
    ارسال فایل (ویدیو یا document) به کاربر
    """
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
        
        # تشخیص نوع فایل و ارسال مناسب
        try:
            # سعی می‌کنیم ویدیو ارسال کنیم
            await context.bot.send_video(
                user_id, 
                file_id, 
                caption=f"🎬 {title}\n🔑 کد: {video_key}",
                reply_markup=get_main_keyboard()
            )
        except BadRequest:
            # اگر ویدیو نبود، سعی می‌کنیم document ارسال کنیم
            try:
                await context.bot.send_document(
                    user_id,
                    file_id,
                    caption=f"📁 {title}\n🔑 کد: {video_key}",
                    reply_markup=get_main_keyboard()
                )
            except Exception as e:
                logging.error(f"❌ خطا در ارسال document: {e}")
                raise
        
        if message_to_edit:
            await message_to_edit.edit_text("✅ فایل با موفقیت ارسال شد!")
        
        # ثبت کاربر به عنوان عضو
        db.set_user_joined(user_id)
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
            
            # بررسی عضویت فعلی
            logging.info(f"🔍 بررسی عضویت کاربر {user_id}")
            is_member = await check_membership(user_id, context)
            
            if is_member:
                logging.info(f"✅ کاربر {user_id} عضو است، ارسال فایل")
                db.set_user_joined(user_id, user.username, user.first_name)
                await send_video_to_user(context, user_id, video_key)
            else:
                logging.info(f"⚠️ کاربر {user_id} عضو نیست، نمایش پیام عضویت")
                await update.message.reply_text(
                    f"⚠️ برای دریافت فایل باید در کانال ما عضو شوید.\n\n"
                    f"📢 {CHANNEL_USERNAME}\n\n"
                    f"✅ پس از عضویت روی دکمه زیر کلیک کنید:",
                    reply_markup=create_join_keyboard(video_key)
                )
    else:
        # پیام خوشامدگویی معمولی
        await update.message.reply_text(
            f"سلام {user.first_name}! 🤖\n\n"
            f"به ربات دریافت فایل خوش آمدید.\n\n"
            f"🎬 برای دریافت فایل روی لینک مخصوص کلیک کنید.\n"
            f"📢 کانال: {CHANNEL_USERNAME}\n\n"
            f"🔍 برای اطلاعات بیشتر از منو استفاده کنید.",
            reply_markup=get_main_keyboard()
        )

# ==================== هندلر دکمه ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    logging.info(f"🔘 دکمه {data} توسط کاربر {user_id} فشرده شد")
    
    if data.startswith("check_"):
        video_key = data.replace("check_", "")
        
        logging.info(f"🔍 بررسی عضویت برای کاربر {user_id} (از طریق دکمه)")
        is_member = await check_membership(user_id, context)
        
        if is_member:
            db.set_user_joined(user_id)
            await send_video_to_user(context, user_id, video_key, query.message)
        else:
            await query.edit_message_text(
                "❌ هنوز در کانال عضو نشده‌اید!\n\n"
                f"لطفاً:\n"
                f"1. روی 'عضویت در کانال' کلیک کنید\n"
                f"2. در کانال {CHANNEL_USERNAME} عضو شوید\n" 
                f"3. سپس دوباره روی 'بررسی عضویت' کلیک کنید\n\n"
                f"🔍 اگر عضو شده‌اید اما این پیام را می‌بینید:\n"
                f"• چند ثانیه صبر کنید\n"
                f"• از کانال خارج و دوباره عضو شوید\n"
                f"• با ادمین تماس بگیرید",
                reply_markup=create_join_keyboard(video_key)
            )
    
    elif data == "stats":
        # نمایش آمار ساده
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
            "3. روی 'بررسی عضویت' کلیک کنید\n"
            "4. فایل دریافت می‌شود\n\n"
            "✅ پس از اولین عضویت:\n"
            "• دیگر نیازی به بررسی نیست\n"
            "• تمام فایل‌ها مستقیم ارسال می‌شوند\n\n"
            f"📢 کانال: {CHANNEL_USERNAME}",
            reply_markup=get_main_keyboard()
        )

# ==================== هندلر آپلود فایل در کانال ====================
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    هندلر برای پست‌های کانال - هم ویدیو و هم document
    """
    if not update.channel_post:
        return
    
    message = update.channel_post
    file_id = None
    file_type = None
    title = ""
    
    # تشخیص نوع فایل
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
        title = message.caption or "ویدیو"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        title = message.caption or message.document.file_name or "فایل"
    else:
        return  # اگر فایل نبود، کاری نکن
    
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
    """تست عضویت"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این دستور فقط برای ادمین است.")
        return
    
    is_member = await check_membership(user_id, context)
    
    await update.message.reply_text(
        f"🔍 تست عضویت:\n\n"
        f"👤 کاربر: {user_id}\n"
        f"📢 کانال ID: {FORCE_CHANNEL_ID}\n"
        f"🔗 لینک: {FORCE_CHANNEL_LINK}\n"
        f"✅ عضو است: {is_member}\n\n"
        f"💡 اگر 'عضو است: False' ولی شما عضو هستید:\n"
        f"• مطمئن شوید ربات در کانال ادمین است\n"
        f"• ID کانال صحیح است"
    )

async def add_file_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور برای افزودن دستی فایل"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        return
    
    if not (update.message.video or update.message.document):
        await update.message.reply_text("لطفاً یک ویدیو یا فایل ارسال کنید.")
        return
    
    # استفاده از همان هندلر کانال
    await handle_channel_post(update, context)

# ==================== اجرای ربات ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    logging.info("🚀 شروع ربات...")
    logging.info(f"📢 کانال ID: {FORCE_CHANNEL_ID}")
    logging.info(f"🔗 لینک کانال: {FORCE_CHANNEL_LINK}")
    logging.info(f"👑 ادمین: {ADMIN_ID}")
    
    app = Application.builder().token(TOKEN).build()
    
    # هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CommandHandler("add", add_file_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # هندلر پست‌های کانال (هم ویدیو و هم document)
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL), 
        handle_channel_post
    ))
    
    logging.info("✅ ربات آماده است")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
