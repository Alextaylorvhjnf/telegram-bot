import os
import logging
import sqlite3
import secrets
import string
import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from telegram.error import BadRequest

# ==================== تنظیمات ====================
TOKEN = "8519774430:AAEDJQXrfj4x7nMmmI8X8EfKj2ipIqxAE8g"
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
                view_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_downloads INTEGER DEFAULT 0
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_key TEXT,
                viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS sent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_id INTEGER,
                video_key TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        cursor = self.conn.execute('SELECT file_id, title, view_count FROM videos WHERE unique_key = ?', (unique_key,))
        result = cursor.fetchone()
        if result:
            return {
                'file_id': result[0], 
                'title': result[1], 
                'view_count': result[2]
            }
        return None
    
    def get_all_videos(self):
        cursor = self.conn.execute('SELECT unique_key, title, view_count FROM videos ORDER BY created_at DESC')
        return cursor.fetchall()
    
    def increment_view_count(self, unique_key):
        self.conn.execute('UPDATE videos SET view_count = view_count + 1 WHERE unique_key = ?', (unique_key,))
        self.conn.commit()
    
    def update_user(self, user_id, username="", first_name=""):
        self.conn.execute(
            'INSERT OR REPLACE INTO users (user_id, username, first_name, last_seen) VALUES (?, ?, ?, CURRENT_TIMESTAMP)', 
            (user_id, username, first_name)
        )
        self.conn.commit()
    
    def increment_user_downloads(self, user_id):
        self.conn.execute('UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def record_user_view(self, user_id, video_key):
        self.conn.execute('INSERT INTO user_views (user_id, video_key) VALUES (?, ?)', (user_id, video_key))
        self.conn.commit()
    
    def save_sent_message(self, user_id, message_id, video_key):
        self.conn.execute('INSERT INTO sent_messages (user_id, message_id, video_key) VALUES (?, ?, ?)', 
                         (user_id, message_id, video_key))
        self.conn.commit()
    
    def get_sent_messages(self):
        cursor = self.conn.execute('SELECT id, user_id, message_id, video_key FROM sent_messages')
        return cursor.fetchall()
    
    def delete_sent_message(self, message_id):
        self.conn.execute('DELETE FROM sent_messages WHERE message_id = ?', (message_id,))
        self.conn.commit()

db = Database()

# ==================== ابزارهای کمکی ====================
def generate_key():
    return 'vid_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

def create_join_keyboard(video_key=None):
    buttons = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=FORCE_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ تأیید عضویت", callback_data=f"check_{video_key}" if video_key else "check")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ])

# ==================== بررسی عضویت ====================
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی عضویت کاربر در کانال"""
    try:
        logging.info(f"🔍 بررسی عضویت کاربر {user_id}")
        
        member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL_ID, user_id=user_id)
        status = member.status
        
        logging.info(f"👤 وضعیت کاربر {user_id}: {status}")
        
        if status in ['member', 'administrator', 'creator']:
            logging.info(f"✅ کاربر {user_id} عضو است")
            return True
        
        logging.warning(f"❌ کاربر {user_id} عضو نیست. وضعیت: {status}")
        return False
            
    except BadRequest as e:
        logging.error(f"❌ خطا در بررسی عضویت: {e}")
        return False
        
    except Exception as e:
        logging.error(f"❌ خطای غیرمنتظره در بررسی عضویت: {e}")
        return False

# ==================== حذف خودکار پیام‌ها ====================
async def delete_old_messages(context: ContextTypes.DEFAULT_TYPE):
    """حذف خودکار پیام‌های ارسال شده بعد از 30 ثانیه"""
    try:
        sent_messages = db.get_sent_messages()
        current_time = datetime.now()
        
        for msg_id, user_id, message_id, video_key in sent_messages:
            try:
                # حذف پیام از چت کاربر
                await context.bot.delete_message(chat_id=user_id, message_id=message_id)
                logging.info(f"✅ پیام {message_id} برای کاربر {user_id} حذف شد")
                
                # حذف از دیتابیس
                db.delete_sent_message(message_id)
                
            except BadRequest as e:
                if "Message to delete not found" in str(e):
                    logging.info(f"⚠️ پیام {message_id} قبلاً حذف شده")
                    db.delete_sent_message(message_id)
                else:
                    logging.error(f"❌ خطا در حذف پیام {message_id}: {e}")
            except Exception as e:
                logging.error(f"❌ خطای غیرمنتظره در حذف پیام: {e}")
                
    except Exception as e:
        logging.error(f"❌ خطا در حذف خودکار پیام‌ها: {e}")

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
        
        # پیام هشدار
        warning_message = await context.bot.send_message(
            user_id,
            "⚠️ **توجه**: این فایل 30 ثانیه دیگر به طور خودکار حذف خواهد شد.\n"
            "💾 بهتر است آن را ذخیره کنید!",
            parse_mode='Markdown'
        )
        
        # ارسال فایل با کپشن ساده (بدون آمار)
        caption = (
            f"🎬 **{title}**\n\n"
            f"⏰ این فایل 30 ثانیه دیگر حذف می‌شود!\n"
            f"💾 برای استفاده بعدی، حتماً ذخیره کنید."
        )
        
        try:
            sent_message = await context.bot.send_video(
                user_id, 
                file_id, 
                caption=caption,
                parse_mode='Markdown'
            )
        except BadRequest:
            sent_message = await context.bot.send_document(
                user_id,
                file_id,
                caption=caption,
                parse_mode='Markdown'
            )
        
        # ذخیره اطلاعات پیام برای حذف خودکار
        db.save_sent_message(user_id, sent_message.message_id, video_key)
        db.save_sent_message(user_id, warning_message.message_id, video_key)
        
        # به‌روزرسانی آمار
        db.increment_view_count(video_key)
        db.increment_user_downloads(user_id)
        db.record_user_view(user_id, video_key)
        
        success_text = "✅ فایل با موفقیت ارسال شد!\n⚠️ یادت نره ذخیره‌اش کنی، 30 ثانیه دیگه حذف میشه!"
        if message_to_edit:
            await message_to_edit.edit_text(success_text)
        else:
            await context.bot.send_message(user_id, success_text)
        
        # برنامه‌ریزی حذف خودکار بعد از 30 ثانیه
        await asyncio.sleep(30)
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=sent_message.message_id)
            await context.bot.delete_message(chat_id=user_id, message_id=warning_message.message_id)
            db.delete_sent_message(sent_message.message_id)
            db.delete_sent_message(warning_message.message_id)
            logging.info(f"✅ فایل {video_key} برای کاربر {user_id} بعد از 30 ثانیه حذف شد")
        except Exception as e:
            logging.error(f"❌ خطا در حذف خودکار فایل: {e}")
        
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
    
    # به‌روزرسانی اطلاعات کاربر
    db.update_user(user_id, user.username, user.first_name)
    
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
            
            # بررسی عضویت کاربر
            is_member = await check_membership(user_id, context)
            
            if is_member:
                logging.info(f"✅ کاربر {user_id} عضو است، ارسال فایل")
                await send_video_to_user(context, user_id, video_key)
            else:
                # نمایش پیام عضویت
                await update.message.reply_text(
                    f"🔒 برای دریافت فایل، لطفاً در کانال ما عضو شوید:\n\n"
                    f"📢 {CHANNEL_USERNAME}\n\n"
                    f"✅ پس از عضویت، روی دکمه زیر کلیک کنید:\n\n"
                    f"⚠️ توجه: اگر از کانال لفت بدید، فایل‌های بعدی براتون ارسال نمیشه!",
                    reply_markup=create_join_keyboard(video_key)
                )
    else:
        # پیام خوشامدگویی معمولی
        await update.message.reply_text(
            f"سلام {user.first_name}! 🤖\n\n"
            f"به ربات دریافت فایل خوش آمدید.\n\n"
            f"🎬 برای دریافت فایل روی لینک مخصوص کلیک کنید.\n"
            f"📢 کانال: {CHANNEL_USERNAME}\n\n"
            f"⚠️ توجه: فایل‌ها 30 ثانیه پس از ارسال به طور خودکار حذف می‌شوند!",
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
        video_key = data.split("_", 1)[1] if "_" in data else None
        
        if not video_key:
            await query.edit_message_text("❌ لینک معتبر نیست.")
            return
        
        # نمایش پیام در حال بررسی
        await query.edit_message_text("🔍 در حال بررسی عضویت... لطفاً صبر کنید.")
        
        # بررسی عضویت
        is_member = await check_membership(user_id, context)
        
        if is_member:
            await query.edit_message_text("✅ عضویت شما تأیید شد!\n\nدر حال ارسال فایل...")
            await send_video_to_user(context, user_id, video_key, query.message)
        else:
            await query.edit_message_text(
                f"❌ عضویت شما تأیید نشد.\n\n"
                f"لطفاً مطمئن شوید:\n"
                f"• در کانال {CHANNEL_USERNAME} عضو شده‌اید\n"
                f"• از اکانت درست استفاده می‌کنید\n\n"
                f"⚠️ اگر از کانال لفت بدید، فایل‌های بعدی براتون ارسال نمیشه!\n\n"
                f"🔗 لینک کانال: {FORCE_CHANNEL_LINK}",
                reply_markup=create_join_keyboard(video_key)
            )
    
    elif data == "help":
        await query.edit_message_text(
            "📖 **راهنمای ربات:**\n\n"
            "🎬 **روش دریافت فایل:**\n"
            "1. روی لینک مخصوص فایل کلیک کنید\n"
            "2. در کانال عضو شوید\n"
            "3. روی دکمه تأیید عضویت کلیک کنید\n"
            "4. فایل دریافت می‌شود\n\n"
            "⚠️ **توجه مهم:**\n"
            "• فایل‌ها 30 ثانیه پس از ارسال حذف می‌شوند\n"
            "• حتماً فایل را ذخیره کنید\n"
            "• اگر از کانال لفت بدید، فایل دریافت نمی‌کنید\n\n"
            f"📢 کانال: {CHANNEL_USERNAME}",
            parse_mode='Markdown',
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
    
    # ایجاد یک کد ثابت برای هر فایل بر اساس محتوای آن
    unique_key = generate_key()
    
    if db.add_video(unique_key, file_id, title):
        # لینک ثابت برای این فایل
        permanent_link = f"https://t.me/{BOT_USERNAME}?start=video_{unique_key}"
        
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"📦 **فایل جدید ذخیره شد!**\n\n"
                f"📁 نوع: {file_type}\n"
                f"🔑 کد ثابت: `{unique_key}`\n"
                f"📝 عنوان: {title}\n"
                f"🔗 لینک ثابت:\n`{permanent_link}`\n\n"
                f"💡 این لینک همیشگی است و منقضی نمی‌شود",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📬 اشتراک‌گذاری لینک", url=permanent_link)
                ]])
            )
            logging.info(f"✅ فایل جدید با کد ثابت {unique_key} ذخیره شد")
        except Exception as e:
            logging.error(f"❌ خطا در ارسال به ادمین: {e}")

# ==================== دستورات ادمین ====================
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این دستور فقط برای ادمین است.")
        return
    
    # جمع‌آوری آمار کامل
    videos = db.get_all_videos()
    
    stats_text = "📊 **آمار کامل ادمین**\n\n"
    stats_text += f"🎬 **تعداد کل ویدیوها:** {len(videos)}\n\n"
    
    total_views = 0
    for unique_key, title, view_count in videos:
        total_views += view_count
        stats_text += f"• {title[:30]}... - {view_count} بازدید\n"
        stats_text += f"  🔗 `https://t.me/{BOT_USERNAME}?start=video_{unique_key}`\n\n"
    
    stats_text += f"👁️ **تعداد کل بازدیدها:** {total_views}"
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def list_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست تمام ویدیوها با لینک‌های ثابت"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این دستور فقط برای ادمین است.")
        return
    
    videos = db.get_all_videos()
    
    if not videos:
        await update.message.reply_text("📭 هیچ فایلی در دیتابیس وجود ندارد.")
        return
    
    message_text = "📋 **لیست فایل‌ها با لینک‌های ثابت:**\n\n"
    
    for i, (unique_key, title, view_count) in enumerate(videos, 1):
        permanent_link = f"https://t.me/{BOT_USERNAME}?start=video_{unique_key}"
        message_text += f"{i}. **{title}**\n"
        message_text += f"   👁️ {view_count} بازدید\n"
        message_text += f"   🔗 `{permanent_link}`\n\n"
    
    # اگر متن طولانی شد، آن را به چند قسمت تقسیم کن
    if len(message_text) > 4000:
        parts = [message_text[i:i+4000] for i in range(0, len(message_text), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode='Markdown')
    else:
        await update.message.reply_text(message_text, parse_mode='Markdown')

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
        
        # ارسال پیام تأیید
        await context.bot.send_message(
            target_user_id,
            "✅ دسترسی شما توسط ادمین تأیید شد!\n\n"
            "اکنون می‌توانید از لینک‌های فایل استفاده کنید."
        )
        
        await update.message.reply_text(f"✅ کاربر {target_user_id} تأیید شد.")
        
    except ValueError:
        await update.message.reply_text("❌ ID کاربر نامعتبر است.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال پیام: {e}")

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
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("list", list_videos))
    app.add_handler(CommandHandler("approve", manual_approve_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # هندلر پست‌های کانال
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL), 
        handle_channel_post
    ))
    
    # Job Queue برای حذف خودکار پیام‌های قدیمی
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(delete_old_messages, interval=60, first=10)  # هر 1 دقیقه چک کن
    
    logging.info("✅ ربات آماده است")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
