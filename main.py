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

# ==================== دیتابیس پیشرفته ====================
class PermanentDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('permanent_bot.db', check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        # جدول ویدیوها با لینک‌های همیشگی
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS permanent_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_key TEXT UNIQUE,
                file_id TEXT NOT NULL,
                title TEXT,
                description TEXT,
                view_count INTEGER DEFAULT 0,
                download_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # جدول کاربران
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS permanent_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_downloads INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # جدول تاریخچه دسترسی‌ها
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS access_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_key TEXT,
                access_type TEXT, -- 'view' یا 'download'
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES permanent_users(user_id),
                FOREIGN KEY (video_key) REFERENCES permanent_videos(unique_key)
            )
        ''')
        
        # جدول لینک‌های همیشگی
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS permanent_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_key TEXT UNIQUE,
                permanent_url TEXT UNIQUE,
                short_code TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_key) REFERENCES permanent_videos(unique_key)
            )
        ''')
        
        # ایندکس برای بهبود عملکرد
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_videos_key ON permanent_videos(unique_key)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_links_key ON permanent_links(video_key)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_access_user ON access_history(user_id)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_access_video ON access_history(video_key)')
        
        self.conn.commit()
        logging.info("✅ دیتابیس لینک‌های همیشگی آماده است")
    
    def add_permanent_video(self, unique_key, file_id, title="", description=""):
        """ذخیره فایل با لینک همیشگی"""
        try:
            # ذخیره ویدیو
            self.conn.execute('''
                INSERT OR REPLACE INTO permanent_videos 
                (unique_key, file_id, title, description) 
                VALUES (?, ?, ?, ?)
            ''', (unique_key, file_id, title, description))
            
            # ایجاد لینک همیشگی
            permanent_url = f"https://t.me/{BOT_USERNAME}?start=video_{unique_key}"
            short_code = unique_key  # می‌توانید کد کوتاه‌تر ایجاد کنید
            
            self.conn.execute('''
                INSERT OR REPLACE INTO permanent_links 
                (video_key, permanent_url, short_code) 
                VALUES (?, ?, ?)
            ''', (unique_key, permanent_url, short_code))
            
            self.conn.commit()
            logging.info(f"✅ فایل با لینک همیشگی ذخیره شد: {unique_key}")
            return True, permanent_url
        except Exception as e:
            logging.error(f"❌ خطا در ذخیره فایل همیشگی: {e}")
            return False, None
    
    def get_permanent_video(self, unique_key):
        """دریافت فایل با کلید یکتا"""
        cursor = self.conn.execute('''
            SELECT file_id, title, description, view_count, download_count, created_at 
            FROM permanent_videos 
            WHERE unique_key = ? AND is_active = 1
        ''', (unique_key,))
        
        result = cursor.fetchone()
        if result:
            return {
                'file_id': result[0], 
                'title': result[1], 
                'description': result[2],
                'view_count': result[3],
                'download_count': result[4],
                'created_at': result[5]
            }
        return None
    
    def get_all_permanent_videos(self):
        """دریافت تمام فایل‌های همیشگی"""
        cursor = self.conn.execute('''
            SELECT v.unique_key, v.title, v.view_count, v.download_count, v.created_at, l.permanent_url
            FROM permanent_videos v
            LEFT JOIN permanent_links l ON v.unique_key = l.video_key
            WHERE v.is_active = 1
            ORDER BY v.created_at DESC
        ''')
        return cursor.fetchall()
    
    def increment_view_count(self, unique_key):
        """افزایش تعداد بازدید"""
        self.conn.execute('''
            UPDATE permanent_videos 
            SET view_count = view_count + 1, last_accessed = CURRENT_TIMESTAMP 
            WHERE unique_key = ?
        ''', (unique_key,))
        self.conn.commit()
    
    def increment_download_count(self, unique_key):
        """افزایش تعداد دانلود"""
        self.conn.execute('''
            UPDATE permanent_videos 
            SET download_count = download_count + 1, last_accessed = CURRENT_TIMESTAMP 
            WHERE unique_key = ?
        ''', (unique_key,))
        self.conn.commit()
    
    def update_or_create_user(self, user_id, username="", first_name=""):
        """به‌روزرسانی یا ایجاد کاربر"""
        self.conn.execute('''
            INSERT OR REPLACE INTO permanent_users 
            (user_id, username, first_name, last_seen) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, username, first_name))
        self.conn.commit()
    
    def increment_user_downloads(self, user_id):
        """افزایش تعداد دانلودهای کاربر"""
        self.conn.execute('''
            UPDATE permanent_users 
            SET total_downloads = total_downloads + 1, last_seen = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()
    
    def record_access(self, user_id, video_key, access_type="view"):
        """ثبت تاریخچه دسترسی"""
        self.conn.execute('''
            INSERT INTO access_history (user_id, video_key, access_type)
            VALUES (?, ?, ?)
        ''', (user_id, video_key, access_type))
        self.conn.commit()
    
    def search_videos(self, keyword):
        """جستجو در فایل‌ها"""
        cursor = self.conn.execute('''
            SELECT unique_key, title, description, view_count
            FROM permanent_videos 
            WHERE (title LIKE ? OR description LIKE ?) AND is_active = 1
            ORDER BY created_at DESC
        ''', (f'%{keyword}%', f'%{keyword}%'))
        return cursor.fetchall()
    
    def get_video_stats(self, unique_key):
        """دریافت آمار یک فایل"""
        cursor = self.conn.execute('''
            SELECT v.title, v.view_count, v.download_count, v.created_at,
                   COUNT(DISTINCT ah.user_id) as unique_users
            FROM permanent_videos v
            LEFT JOIN access_history ah ON v.unique_key = ah.video_key
            WHERE v.unique_key = ?
            GROUP BY v.unique_key
        ''', (unique_key,))
        
        result = cursor.fetchone()
        if result:
            return {
                'title': result[0],
                'view_count': result[1],
                'download_count': result[2],
                'created_at': result[3],
                'unique_users': result[4] or 0
            }
        return None
    
    def backup_database(self):
        """پشتیبان‌گیری از دیتابیس"""
        try:
            backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_conn = sqlite3.connect(backup_file)
            self.conn.backup(backup_conn)
            backup_conn.close()
            logging.info(f"✅ پشتیبان‌گیری انجام شد: {backup_file}")
            return backup_file
        except Exception as e:
            logging.error(f"❌ خطا در پشتیبان‌گیری: {e}")
            return None

# ایجاد نمونه دیتابیس
db = PermanentDatabase()

# ==================== ابزارهای کمکی ====================
def generate_permanent_key():
    """تولید کلید یکتا برای لینک همیشگی"""
    timestamp = datetime.now().strftime("%Y%m%d")
    random_part = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"perm_{timestamp}_{random_part}"

def generate_short_key():
    """تولید کلید کوتاه برای اشتراک‌گذاری"""
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

def create_join_keyboard(video_key=None):
    """ایجاد دکمه‌های عضویت"""
    buttons = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=FORCE_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ تأیید عضویت", callback_data=f"check_{video_key}" if video_key else "check")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_main_keyboard():
    """منوی اصلی"""
    buttons = [
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")],
        [InlineKeyboardButton("🔍 جستجوی فایل", callback_data="search")],
        [InlineKeyboardButton("📊 آمار من", callback_data="my_stats")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_admin_keyboard():
    """منوی ادمین"""
    buttons = [
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
        [InlineKeyboardButton("📋 لیست فایل‌ها", callback_data="admin_list")],
        [InlineKeyboardButton("🔄 پشتیبان‌گیری", callback_data="admin_backup")],
        [InlineKeyboardButton("🔍 جستجو در فایل‌ها", callback_data="admin_search")]
    ]
    return InlineKeyboardMarkup(buttons)

# ==================== بررسی عضویت ====================
async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی عضویت کاربر در کانال"""
    try:
        logging.info(f"🔍 بررسی عضویت کاربر {user_id}")
        
        member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL_ID, user_id=user_id)
        status = member.status
        
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

# ==================== ارسال فایل همیشگی ====================
async def send_permanent_video(context, user_id, video_key, message_to_edit=None):
    """ارسال فایل با لینک همیشگی"""
    try:
        # دریافت اطلاعات فایل از دیتابیس
        video_data = db.get_permanent_video(video_key)
        
        if not video_data:
            error_text = "❌ فایل مورد نظر پیدا نشد. ممکن است حذف شده یا لینک نامعتبر باشد."
            if message_to_edit:
                await message_to_edit.edit_text(error_text)
            else:
                await context.bot.send_message(user_id, error_text)
            return False
        
        file_id = video_data['file_id']
        title = video_data['title'] or "فایل"
        description = video_data.get('description', '')
        
        # به‌روزرسانی آمار
        db.increment_view_count(video_key)
        db.increment_download_count(video_key)
        db.increment_user_downloads(user_id)
        db.record_access(user_id, video_key, "download")
        
        # ایجاد کپشن با اطلاعات کامل
        caption = f"🎬 **{title}**\n\n"
        
        if description:
            caption += f"📝 {description}\n\n"
        
        caption += (
            f"📊 **آمار فایل:**\n"
            f"👁️ بازدید: {video_data['view_count'] + 1}\n"
            f"💾 دانلود: {video_data['download_count'] + 1}\n"
            f"📅 تاریخ آپلود: {video_data['created_at'].split()[0] if video_data['created_at'] else 'نامشخص'}\n\n"
            f"🔗 **لینک همیشگی این فایل:**\n"
            f"`https://t.me/{BOT_USERNAME}?start=video_{video_key}`\n\n"
            f"💡 این لینک همیشگی است و همیشه کار می‌کند!"
        )
        
        # ارسال فایل
        try:
            # سعی در ارسال به عنوان ویدیو
            await context.bot.send_video(
                user_id, 
                file_id, 
                caption=caption,
                parse_mode='Markdown',
                supports_streaming=True
            )
            sent_as_video = True
        except BadRequest:
            # اگر ویدیو نبود، به عنوان سند ارسال کن
            await context.bot.send_document(
                user_id,
                file_id,
                caption=caption,
                parse_mode='Markdown'
            )
            sent_as_video = False
        
        # پیام تأیید ارسال
        success_text = (
            f"✅ **فایل با موفقیت ارسال شد!**\n\n"
            f"📁 **عنوان:** {title}\n"
            f"🔗 **لینک همیشگی:**\n"
            f"`https://t.me/{BOT_USERNAME}?start=video_{video_key}`\n\n"
            f"💾 می‌توانید این فایل را ذخیره کنید و هر زمان خواستید دوباره از طریق همین لینک دریافت کنید."
        )
        
        if message_to_edit:
            await message_to_edit.edit_text(success_text, parse_mode='Markdown')
        else:
            await context.bot.send_message(user_id, success_text, parse_mode='Markdown')
        
        logging.info(f"✅ فایل همیشگی {video_key} برای کاربر {user_id} ارسال شد")
        return True
        
    except Exception as e:
        logging.error(f"❌ خطا در ارسال فایل همیشگی: {e}")
        
        error_text = (
            "❌ خطا در ارسال فایل.\n\n"
            "⚠️ لطفاً:\n"
            "1. اتصال اینترنت خود را بررسی کنید\n"
            "2. چند لحظه صبر کنید و دوباره تلاش کنید\n"
            "3. اگر مشکل ادامه داشت، به ادمین گزارش دهید"
        )
        
        if message_to_edit:
            await message_to_edit.edit_text(error_text)
        else:
            await context.bot.send_message(user_id, error_text)
        
        return False

# ==================== هندلر استارت با لینک همیشگی ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    logging.info(f"🚀 کاربر {user_id} دستور /start را اجرا کرد")
    
    # به‌روزرسانی اطلاعات کاربر
    db.update_or_create_user(user_id, user.username, user.first_name)
    
    # اگر آرگومان دارد (یعنی از لینک همیشگی آمده)
    if context.args:
        start_arg = context.args[0]
        
        if start_arg.startswith("video_"):
            video_key = start_arg.replace("video_", "")
            logging.info(f"🎬 درخواست فایل همیشگی {video_key} توسط کاربر {user_id}")
            
            # بررسی وجود فایل
            if not db.get_permanent_video(video_key):
                await update.message.reply_text(
                    "❌ لینک معتبر نیست یا فایل حذف شده است.\n\n"
                    "⚠️ اگر این لینک قبلاً کار می‌کرد، ممکن است فایل به طور دائم حذف شده باشد.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            # بررسی عضویت کاربر
            is_member = await check_membership(user_id, context)
            
            if is_member:
                logging.info(f"✅ کاربر {user_id} عضو است، ارسال فایل همیشگی")
                await send_permanent_video(context, user_id, video_key)
            else:
                # نمایش پیام عضویت
                await update.message.reply_text(
                    f"🔒 **برای دریافت فایل، لطفاً در کانال ما عضو شوید:**\n\n"
                    f"📢 {CHANNEL_USERNAME}\n\n"
                    f"✅ پس از عضویت، روی دکمه زیر کلیک کنید:\n\n"
                    f"⚠️ **توجه:**\n"
                    f"• این لینک همیشگی است و منقضی نمی‌شود\n"
                    f"• می‌توانید بعداً هم از همین لینک استفاده کنید\n"
                    f"• اگر از کانال لفت بدید، دسترسی قطع می‌شود\n\n"
                    f"🔗 **لینک همیشگی این فایل:**\n"
                    f"`https://t.me/{BOT_USERNAME}?start=video_{video_key}`",
                    reply_markup=create_join_keyboard(video_key),
                    parse_mode='Markdown'
                )
        elif start_arg == "admin":
            if user_id == ADMIN_ID:
                await update.message.reply_text(
                    "👑 **پنل مدیریت ادمین**\n\n"
                    "لطفاً یکی از گزینه‌ها را انتخاب کنید:",
                    reply_markup=get_admin_keyboard()
                )
    else:
        # پیام خوشامدگویی معمولی
        await update.message.reply_text(
            f"👋 **سلام {user.first_name}!** 🤖\n\n"
            f"**به ربات دریافت فایل با لینک‌های همیشگی خوش آمدید!**\n\n"
            f"🎬 **ویژگی‌های ربات:**\n"
            f"• 🔗 **لینک‌های همیشگی** (هرگز منقضی نمی‌شوند)\n"
            f"• 💾 **ذخیره دائمی فایل‌ها**\n"
            f"• 📊 **آمار دقیق بازدید و دانلود**\n"
            f"• 🔍 **قابلیت جستجو در فایل‌ها**\n\n"
            f"📢 **کانال ما:** {CHANNEL_USERNAME}\n\n"
            f"💡 **نحوه استفاده:**\n"
            f"روی لینک مخصوص هر فایل کلیک کنید، در کانال عضو شوید و فایل را دریافت کنید.\n"
            f"لینک‌ها همیشگی هستند و می‌توانید بارها استفاده کنید!",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
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
            await send_permanent_video(context, user_id, video_key, query.message)
        else:
            await query.edit_message_text(
                f"❌ عضویت شما تأیید نشد.\n\n"
                f"**لطفاً مطمئن شوید:**\n"
                f"• در کانال {CHANNEL_USERNAME} عضو شده‌اید\n"
                f"• از اکانت درست استفاده می‌کنید\n\n"
                f"⚠️ **توجه:** اگر از کانال لفت بدید، دسترسی شما قطع می‌شود!\n\n"
                f"🔗 **لینک کانال:** {FORCE_CHANNEL_LINK}\n\n"
                f"🔗 **لینک همیشگی این فایل:**\n"
                f"`https://t.me/{BOT_USERNAME}?start=video_{video_key}`",
                reply_markup=create_join_keyboard(video_key),
                parse_mode='Markdown'
            )
    
    elif data == "help":
        await query.edit_message_text(
            "📖 **راهنمای کامل ربات**\n\n"
            "🎬 **روش دریافت فایل:**\n"
            "1. روی لینک مخصوص فایل کلیک کنید\n"
            "2. در کانال عضو شوید\n"
            "3. روی دکمه «تأیید عضویت» کلیک کنید\n"
            "4. فایل دریافت می‌شود\n\n"
            "🔗 **لینک‌های همیشگی:**\n"
            "• لینک‌های فایل‌ها همیشگی هستند\n"
            "• هرگز منقضی نمی‌شوند\n"
            "• می‌توانید بارها استفاده کنید\n"
            "• فایل‌ها به طور دائمی ذخیره می‌شوند\n\n"
            "📊 **آمار و گزارش:**\n"
            "• تعداد بازدید هر فایل\n"
            "• تعداد دانلود\n"
            "• تاریخ آپلود\n"
            "• کاربران منحصر به فرد\n\n"
            "🔍 **جستجو:**\n"
            "می‌توانید در بین فایل‌ها جستجو کنید\n\n"
            f"📢 **کانال اصلی:** {CHANNEL_USERNAME}\n\n"
            "💡 **نکته مهم:**\n"
            "برای حفظ دسترسی، باید در کانال عضو بمانید!",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    
    elif data == "search":
        await query.edit_message_text(
            "🔍 **جستجوی فایل**\n\n"
            "برای جستجو در بین فایل‌ها، لطفاً از دستور زیر استفاده کنید:\n\n"
            "`/search <کلیدواژه>`\n\n"
            "مثال:\n"
            "`/search آموزش پایتون`\n\n"
            "یا برای دیدن لیست همه فایل‌ها:\n"
            "`/allfiles`",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )
    
    elif data == "my_stats":
        user_stats = db.conn.execute(
            'SELECT total_downloads, join_date FROM permanent_users WHERE user_id = ?', 
            (user_id,)
        ).fetchone()
        
        if user_stats:
            await query.edit_message_text(
                f"📊 **آمار شما**\n\n"
                f"👤 کاربر: {query.from_user.first_name}\n"
                f"🆔 ID: {user_id}\n"
                f"💾 مجموع دانلودها: {user_stats[0]}\n"
                f"📅 تاریخ عضویت: {user_stats[1].split()[0] if user_stats[1] else 'نامشخص'}\n\n"
                f"🔗 برای دریافت فایل‌های جدید، روی لینک‌های همیشگی کلیک کنید.",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
    
    elif data == "admin_stats":
        if user_id == ADMIN_ID:
            await admin_stats_callback(query)
    
    elif data == "admin_list":
        if user_id == ADMIN_ID:
            await list_videos_callback(query)
    
    elif data == "admin_backup":
        if user_id == ADMIN_ID:
            await query.edit_message_text("🔄 در حال ایجاد پشتیبان...")
            backup_file = db.backup_database()
            if backup_file:
                await query.edit_message_text(f"✅ پشتیبان‌گیری با موفقیت انجام شد.\n\nفایل: `{backup_file}`", parse_mode='Markdown')
            else:
                await query.edit_message_text("❌ خطا در ایجاد پشتیبان.")
    
    elif data == "admin_search":
        if user_id == ADMIN_ID:
            await query.edit_message_text(
                "🔍 **جستجوی ادمین**\n\n"
                "برای جستجو در بین همه فایل‌ها از دستور زیر استفاده کنید:\n\n"
                "`/adminsearch <کلیدواژه>`\n\n"
                "مثال:\n"
                "`/adminsearch ویدیو آموزشی`",
                parse_mode='Markdown'
            )

# ==================== آپلود فایل همیشگی ====================
async def handle_permanent_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آپلود فایل جدید با لینک همیشگی"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این قابلیت فقط برای ادمین در دسترس است.")
        return
    
    message = update.message
    
    # بررسی نوع پیام
    if message.video:
        file_obj = message.video
        file_type = "video"
    elif message.document:
        file_obj = message.document
        file_type = "document"
    elif message.photo:
        # برای عکس‌ها، آخرین عکس (با کیفیت بالاتر)
        file_obj = message.photo[-1]
        file_type = "photo"
    else:
        await update.message.reply_text(
            "❌ لطفاً یک فایل (ویدیو، سند یا عکس) ارسال کنید.\n\n"
            "📝 **نکته:** می‌توانید برای فایل توضیح نیز ارسال کنید."
        )
        return
    
    file_id = file_obj.file_id
    title = message.caption or file_obj.file_name or "فایل بدون عنوان"
    
    # تولید کلید یکتا برای لینک همیشگی
    unique_key = generate_permanent_key()
    
    # ذخیره فایل با لینک همیشگی
    success, permanent_url = db.add_permanent_video(
        unique_key, 
        file_id, 
        title, 
        message.caption or ""
    )
    
    if success:
        # ایجاد لینک کوتاه‌تر برای اشتراک‌گذاری
        short_url = f"https://t.me/{BOT_USERNAME}?start=video_{unique_key}"
        
        response_text = (
            f"✅ **فایل با لینک همیشگی ذخیره شد!**\n\n"
            f"📁 **عنوان:** {title}\n"
            f"🔤 **نوع:** {file_type}\n"
            f"🔑 **کلید یکتا:** `{unique_key}`\n"
            f"📅 **تاریخ ایجاد:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🔗 **لینک همیشگی:**\n`{short_url}`\n\n"
            f"📊 **برای اشتراک‌گذاری:**\n"
            f"می‌توانید این لینک را با دیگران به اشتراک بگذارید.\n"
            f"این لینک همیشگی است و هرگز منقضی نمی‌شود!"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📬 اشتراک‌گذاری لینک", url=short_url)],
            [InlineKeyboardButton("📊 مشاهده آمار", callback_data=f"stats_{unique_key}")]
        ])
        
        await update.message.reply_text(
            response_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
        logging.info(f"✅ فایل همیشگی جدید ذخیره شد: {unique_key}")
    else:
        await update.message.reply_text(
            "❌ خطا در ذخیره فایل. لطفاً دوباره تلاش کنید.\n\n"
            "⚠️ ممکن است فایل تکراری باشد یا مشکلی در دیتابیس وجود داشته باشد."
        )

# ==================== دستورات ادمین ====================
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور آمار ادمین"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این دستور فقط برای ادمین است.")
        return
    
    await admin_stats_callback(update.message)

async def admin_stats_callback(message_or_query):
    """تابع مشترک برای نمایش آمار ادمین"""
    # جمع‌آوری آمار کامل
    videos = db.get_all_permanent_videos()
    
    # آمار کلی
    total_videos = len(videos)
    total_views = sum(v[2] for v in videos)
    total_downloads = sum(v[3] for v in videos)
    
    # قدیمی‌ترین و جدیدترین فایل
    if videos:
        oldest = min(videos, key=lambda x: x[4] if x[4] else '9999-99-99')
        newest = max(videos, key=lambda x: x[4] if x[4] else '0000-00-00')
    else:
        oldest = newest = None
    
    stats_text = "📊 **آمار کامل ادمین - لینک‌های همیشگی**\n\n"
    stats_text += f"🎬 **تعداد کل فایل‌ها:** {total_videos}\n"
    stats_text += f"👁️ **مجموع بازدیدها:** {total_views}\n"
    stats_text += f"💾 **مجموع دانلودها:** {total_downloads}\n\n"
    
    if oldest:
        stats_text += f"📅 **قدیمی‌ترین فایل:**\n"
        stats_text += f"   • {oldest[1][:30]}...\n"
        stats_text += f"   • تاریخ: {oldest[4].split()[0] if oldest[4] else 'نامشخص'}\n"
        stats_text += f"   • بازدید: {oldest[2]}\n\n"
    
    if newest:
        stats_text += f"📅 **جدیدترین فایل:**\n"
        stats_text += f"   • {newest[1][:30]}...\n"
        stats_text += f"   • تاریخ: {newest[4].split()[0] if newest[4] else 'نامشخص'}\n"
        stats_text += f"   • بازدید: {newest[2]}\n\n"
    
    stats_text += "🔗 **آخرین فایل‌ها:**\n"
    
    for i, (unique_key, title, view_count, download_count, created_at, url) in enumerate(videos[:5], 1):
        stats_text += f"{i}. {title[:25]}...\n"
        stats_text += f"   👁️ {view_count} | 💾 {download_count}\n"
        stats_text += f"   🔗 `{url}`\n\n"
    
    if total_videos > 5:
        stats_text += f"📋 و {total_videos - 5} فایل دیگر...\n\n"
    
    stats_text += "💡 برای مشاهده لیست کامل از `/list` استفاده کنید."
    
    if isinstance(message_or_query, Update):
        await message_or_query.message.reply_text(stats_text, parse_mode='Markdown')
    else:
        await message_or_query.edit_message_text(stats_text, parse_mode='Markdown')

async def list_videos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست تمام فایل‌های همیشگی"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ این دستور فقط برای ادمین است.")
        return
    
    await list_videos_callback(update.message)

async def list_videos_callback(message_or_query):
    """تابع مشترک برای لیست فایل‌ها"""
    videos = db.get_all_permanent_videos()
    
    if not videos:
        response_text = "📭 **هیچ فایلی در دیتابیس وجود ندارد.**\n\n"
        response_text += "💡 فایل‌ها را با ارسال به ربات آپلود کنید."
        
        if isinstance(message_or_query, Update):
            await message_or_query.message.reply_text(response_text, parse_mode='Markdown')
        else:
            await message_or_query.edit_message_text(response_text, parse_mode='Markdown')
        return
    
    message_text = "📋 **لیست فایل‌های همیشگی:**\n\n"
    
    for i, (unique_key, title, view_count, download_count, created_at, url) in enumerate(videos, 1):
        message_text += f"{i}. **{title}**\n"
        message_text += f"   👁️ {view_count} بازدید | 💾 {download_count} دانلود\n"
        message_text += f"   📅 {created_at.split()[0] if created_at else 'نامشخص'}\n"
        message_text += f"   🔗 `{url}`\n\n"
    
    # اگر متن طولانی شد، آن را به چند قسمت تقسیم کن
    if len(message_text) > 4000:
        parts = [message_text[i:i+4000] for i in range(0, len(message_text), 4000)]
        for part in parts:
            if isinstance(message_or_query, Update):
                await message_or_query.message.reply_text(part, parse_mode='Markdown')
            else:
                # برای کال‌بک، فقط اولین قسمت را نمایش بده
                await message_or_query.edit_message_text(part[:4000], parse_mode='Markdown')
                break
    else:
        if isinstance(message_or_query, Update):
            await message_or_query.message.reply_text(message_text, parse_mode='Markdown')
        else:
            await message_or_query.edit_message_text(message_text, parse_mode='Markdown')

async def search_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جستجو در فایل‌ها"""
    if not context.args:
        await update.message.reply_text(
            "🔍 **لطفاً کلیدواژه جستجو را وارد کنید:**\n\n"
            "مثال:\n"
            "`/search آموزش`\n"
            "`/search python`\n"
            "`/search ویدیو`",
            parse_mode='Markdown'
        )
        return
    
    keyword = ' '.join(context.args)
    results = db.search_videos(keyword)
    
    if not results:
        await update.message.reply_text(
            f"🔍 **نتیجه‌ای برای '{keyword}' پیدا نشد.**\n\n"
            "💡 می‌توانید از کلمات کلیدی مختلف استفاده کنید.",
            parse_mode='Markdown'
        )
        return
    
    message_text = f"🔍 **نتایج جستجو برای '{keyword}':**\n\n"
    
    for i, (unique_key, title, description, view_count) in enumerate(results[:10], 1):
        message_text += f"{i}. **{title}**\n"
        if description:
            message_text += f"   📝 {description[:50]}...\n"
        message_text += f"   👁️ {view_count} بازدید\n"
        message_text += f"   🔗 `/start video_{unique_key}`\n\n"
    
    if len(results) > 10:
        message_text += f"📋 و {len(results) - 10} نتیجه دیگر...\n\n"
    
    message_text += "💡 برای دریافت فایل، روی لینک کلیک کنید یا آن را کپی کنید."
    
    await update.message.reply_text(message_text, parse_mode='Markdown')

async def show_all_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش تمام فایل‌های موجود"""
    videos = db.get_all_permanent_videos()
    
    if not videos:
        await update.message.reply_text(
            "📭 **هنوز فایلی آپلود نشده است.**\n\n"
            "💡 ادمین می‌تواند فایل‌ها را آپلود کند.",
            parse_mode='Markdown'
        )
        return
    
    # فقط 10 فایل آخر را نمایش بده
    recent_videos = videos[:10]
    
    message_text = "📋 **آخرین فایل‌های همیشگی:**\n\n"
    
    for i, (unique_key, title, view_count, download_count, created_at, url) in enumerate(recent_videos, 1):
        message_text += f"{i}. **{title}**\n"
        message_text += f"   👁️ {view_count} بازدید | 💾 {download_count} دانلود\n"
        message_text += f"   📅 {created_at.split()[0] if created_at else 'نامشخص'}\n"
        message_text += f"   🔗 `/start video_{unique_key}`\n\n"
    
    if len(videos) > 10:
        message_text += f"📋 و {len(videos) - 10} فایل دیگر...\n\n"
    
    message_text += "💡 برای دریافت فایل، دستور بالا را کپی و ارسال کنید."
    
    await update.message.reply_text(message_text, parse_mode='Markdown')

async def get_file_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت اطلاعات یک فایل"""
    if not context.args:
        await update.message.reply_text(
            "📄 **لطفاً کلید فایل را وارد کنید:**\n\n"
            "مثال:\n"
            "`/info video_perm_20231201_abc123`\n\n"
            "💡 کلید فایل را از انتهای لینک می‌توانید پیدا کنید.",
            parse_mode='Markdown'
        )
        return
    
    video_key = context.args[0].replace("video_", "")
    video_data = db.get_permanent_video(video_key)
    
    if not video_data:
        await update.message.reply_text(
            "❌ **فایل مورد نظر پیدا نشد.**\n\n"
            "⚠️ ممکن است:\n"
            "• لینک اشتباه باشد\n"
            "• فایل حذف شده باشد\n"
            "• کلید فایل تغییر کرده باشد",
            parse_mode='Markdown'
        )
        return
    
    stats = db.get_video_stats(video_key)
    
    message_text = f"📄 **اطلاعات فایل:**\n\n"
    message_text += f"📁 **عنوان:** {video_data['title']}\n"
    
    if video_data.get('description'):
        message_text += f"📝 **توضیحات:** {video_data['description']}\n"
    
    if stats:
        message_text += f"📊 **آمار:**\n"
        message_text += f"   👁️ بازدید: {stats['view_count']}\n"
        message_text += f"   💾 دانلود: {stats['download_count']}\n"
        message_text += f"   👥 کاربران منحصر به فرد: {stats['unique_users']}\n"
        message_text += f"   📅 تاریخ آپلود: {stats['created_at'].split()[0] if stats['created_at'] else 'نامشخص'}\n"
    
    message_text += f"\n🔗 **لینک همیشگی:**\n"
    message_text += f"`https://t.me/{BOT_USERNAME}?start=video_{video_key}`\n\n"
    message_text += f"💡 این لینک همیشگی است و هرگز منقضی نمی‌شود!"
    
    await update.message.reply_text(message_text, parse_mode='Markdown')

# ==================== اجرای ربات ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    print("=" * 60)
    print("🤖 ربات ارسال فایل با لینک‌های همیشگی")
    print("=" * 60)
    print(f"📱 نام ربات: {BOT_USERNAME}")
    print(f"👑 ادمین اصلی: {ADMIN_ID}")
    print(f"📢 کانال: {CHANNEL_USERNAME}")
    print("=" * 60)
    print("🔗 ویژگی: لینک‌های همیشگی - فایل‌ها هرگز حذف نمی‌شوند!")
    print("=" * 60)
    
    # ایجاد اپلیکیشن
    app = Application.builder().token(TOKEN).build()
    
    # هندلرهای اصلی
    app.add_handler(CommandHandler("start", start))
    
    # هندلرهای کاربران عادی
    app.add_handler(CommandHandler("search", search_videos))
    app.add_handler(CommandHandler("allfiles", show_all_files))
    app.add_handler(CommandHandler("info", get_file_info))
    
    # هندلرهای ادمین
    app.add_handler(CommandHandler("stats", admin_stats_command))
    app.add_handler(CommandHandler("list", list_videos_command))
    app.add_handler(CommandHandler("upload", handle_permanent_upload))
    
    # هندلر دکمه‌ها
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # هندلر آپلود فایل از چت خصوصی (برای ادمین)
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.VIDEO | filters.Document.ALL | filters.PHOTO), 
        handle_permanent_upload
    ))
    
    # هندلر پست‌های کانال (اختیاری - برای آپلود خودکار از کانال)
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL | filters.PHOTO), 
        handle_permanent_upload
    ))
    
    print("✅ ربات با قابلیت لینک‌های همیشگی آماده است...")
    print("🔄 در حال اتصال به سرور تلگرام...")
    
    try:
        app.run_polling(
            drop_pending_updates=True,
            timeout=30,
            pool_timeout=30,
            connect_timeout=30,
            read_timeout=30,
            write_timeout=30,
            allowed_updates=Update.ALL_TYPES
        )
    except KeyboardInterrupt:
        print("\n🛑 ربات توسط کاربر متوقف شد.")
    except Exception as e:
        print(f"❌ خطا در اجرای ربات: {e}")

if __name__ == "__main__":
    main()
