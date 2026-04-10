"""هندلر ربات تلگرام"""
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from telethon import TelegramClient, events
from telethon.tl.custom import Button

from src.config import Config
from src.services import AccountReceiver, ChannelManager, ReferralManager, MessageSender, BotAutomation, BackupManager, ReactionManager, BlockManager
from src.models import AccountCredentials
from src.database import Database, User, Account
from src.utils.validators import extract_telegram_code

logger = logging.getLogger(__name__)

class BotHandler:
    """کلاس مدیریت ربات تلگرام"""
    
    def __init__(self):
        """مقداردهی اولیه"""
        self.bot = TelegramClient(
            'bot_session',
            Config.API_ID,
            Config.API_HASH
        )
        self.receiver = AccountReceiver()
        self.channel_manager = ChannelManager()
        self.referral_manager = ReferralManager()
        self.message_sender = MessageSender()
        self.bot_automation = BotAutomation()
        self.backup_manager = BackupManager()
        self.reaction_manager = ReactionManager()
        self.block_manager = BlockManager()
        self.db = Database(Config.DATABASE_PATH)
        
        # ذخیره وضعیت کاربران
        self.user_states = {}
        
        # ذخیره وضعیت عملیات‌های در حال اجرا (برای لغو)
        self.running_operations = {}
    
    async def _ask_account_count(self, event, user_id, total_accounts: int, next_step: str, operation_name: str):
        """
        پرسیدن تعداد اکانت از کاربر
        
        Args:
            event: رویداد تلگرام
            user_id: آیدی کاربر
            total_accounts: تعداد کل اکانت‌های فعال
            next_step: مرحله بعدی
            operation_name: نام عملیات (برای نمایش)
        """
        self.user_states[user_id]['step'] = next_step
        
        await event.respond(
            f"📊 **انتخاب تعداد اکانت**\n\n"
            f"شما {total_accounts} اکانت فعال دارید.\n\n"
            f"چند تا اکانت برای {operation_name} استفاده شود؟\n\n"
            f"💡 عدد ارسال کنید (مثلاً 5) یا:\n"
            f"• /all برای همه اکانت‌ها",
            buttons=Button.inline("❌ لغو", b"cancel")
        )
    
    def _select_accounts(self, count_input: str, all_accounts: list) -> list:
        """
        انتخاب تعداد مشخصی از اکانت‌ها
        
        Args:
            count_input: ورودی کاربر (عدد یا /all)
            all_accounts: لیست همه اکانت‌ها
            
        Returns:
            لیست اکانت‌های انتخاب شده
            
        Raises:
            ValueError: اگر ورودی نامعتبر باشد
        """
        if count_input.lower() == '/all':
            return all_accounts
        
        count = int(count_input)
        if count <= 0:
            raise ValueError("تعداد باید بیشتر از صفر باشد")
        
        return all_accounts[:min(count, len(all_accounts))]
    
    async def _check_admin_access(self, event) -> bool:
        """
        بررسی دسترسی ادمین
        
        Args:
            event: رویداد تلگرام
            
        Returns:
            True اگر کاربر ادمین یا سازنده باشد
        """
        user_id = event.sender_id
        is_creator = user_id in Config.ADMIN_IDS
        is_admin = await self.db.is_admin(user_id)
        
        if not is_creator and not is_admin:
            await event.answer("⛔️ این قابلیت فقط برای ادمین‌ها در دسترس است!", alert=True)
            return False
        
        return True
    
    async def _check_creator_access(self, event) -> bool:
        """
        بررسی دسترسی سازنده
        
        Args:
            event: رویداد تلگرام
            
        Returns:
            True اگر کاربر سازنده باشد
        """
        user_id = event.sender_id
        is_creator = user_id in Config.ADMIN_IDS
        
        if not is_creator:
            await event.answer("⛔️ این قابلیت فقط برای سازنده در دسترس است!", alert=True)
            return False
        
        return True
    
    async def start(self):
        """راه‌اندازی ربات"""
        # راه‌اندازی دیتابیس
        await self.db.init_db()
        
        # افزودن ادمین‌ها
        for admin_id in Config.ADMIN_IDS:
            await self.db.add_user(User(
                user_id=admin_id,
                is_admin=True
            ))
        
        # بارگذاری کانال بکاپ از دیتابیس
        backup_channel = await self.db.get_setting('backup_channel_id')
        if backup_channel:
            self.backup_manager.set_backup_channel(int(backup_channel))
            logger.info(f"کانال بکاپ از دیتابیس بارگذاری شد: {backup_channel}")
        
        await self.bot.start(bot_token=Config.BOT_TOKEN)
        
        logger.info("ربات راه‌اندازی شد")
        
        # ثبت هندلرها
        self._register_handlers()
        
        # اجرای ربات
        await self.bot.run_until_disconnected()
    
    def _register_handlers(self):
        """ثبت هندلرهای ربات"""
        
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            """هندلر دستور start"""
            # ثبت کاربر
            user = await event.get_sender()
            
            # بررسی دسترسی
            is_creator = user.id in Config.ADMIN_IDS
            is_admin = await self.db.is_admin(user.id)
            
            # سازنده و ادمین‌ها خودکار approved هستن
            is_approved = is_creator or is_admin
            
            # اگر کاربر جدیده، ثبتش میکنیم
            existing_user = await self.db.get_user(user.id)
            request_sent = False  # برای جلوگیری از اسپم
            
            if not existing_user:
                await self.db.add_user(User(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    is_admin=is_admin,
                    is_approved=is_approved
                ))
                
                # اگر کاربر عادیه، فقط یکبار به سازنده اطلاع میدیم
                if not is_creator and not is_admin:
                    request_sent = True
                    for creator_id in Config.ADMIN_IDS:
                        try:
                            await self.bot.send_message(
                                creator_id,
                                f"🔔 **کاربر جدید!**\n\n"
                                f"👤 نام: {user.first_name or 'ندارد'}\n"
                                f"🆔 یوزرنیم: @{user.username or 'ندارد'}\n"
                                f"🔢 آیدی: `{user.id}`\n\n"
                                f"برای تایید دسترسی: `/approve {user.id}`",
                                buttons=[
                                    [Button.inline("✅ تایید دسترسی", f"approve_{user.id}".encode())],
                                    [Button.inline("❌ رد کردن", f"reject_{user.id}".encode())]
                                ]
                            )
                        except:
                            pass
            else:
                # بروزرسانی اطلاعات
                is_approved = existing_user.is_approved or is_creator or is_admin
                await self.db.add_user(User(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    is_admin=is_admin,
                    is_approved=is_approved
                ))
            
            await self.db.log_action('start', user.id)
            
            # اگر کاربر عادی و تایید نشده
            if not is_creator and not is_admin and not is_approved:
                if request_sent:
                    # فقط اولین بار جواب میده
                    await event.respond(
                        "⏳ **درخواست شما ارسال شد**\n\n"
                        "درخواست شما برای استفاده از ربات به سازنده ارسال شد.\n\n"
                        "لطفاً منتظر تایید باشید.\n\n"
                        "پس از تایید، به شما اطلاع داده می‌شود."
                    )
                # دفعات بعدی اصلاً جواب نمیده (ignore)
                return
            
            # منوی اصلی
            if is_creator:
                # منوی کامل برای سازنده (Creator)
                buttons = [
                    [Button.inline("➕ افزودن اکانت", b"add_account"),
                     Button.inline("📋 اکانت‌های من", b"my_accounts")],
                    [Button.inline("🔗 جوین کانال", b"join_channel"), 
                     Button.inline("🚪 لفت کانال", b"leave_channel")],
                    [Button.inline("🤖 استارت رفرال", b"start_referral"),
                     Button.inline("💬 ارسال پیام", b"send_message")],
                    [Button.inline("❤️ ری‌اکشن و سین", b"react_post"),
                     Button.inline("🚫 بلاک/انبلاک", b"block_user")],
                    [Button.inline("🎯 سناریو پیشرفته", b"advanced_scenario")],
                    [Button.inline("⚙️ مدیریت ربات", b"bot_management")],
                    [Button.inline("👑 پنل ادمین", b"admin_panel")]
                ]
                
                welcome_text = (
                    "🔐 **ربات مدیریت اکانت تلگرام**\n\n"
                    "👑 **شما سازنده (Creator) هستید**\n\n"
                    "به ربات خوش آمدید! این ربات می‌تواند:\n\n"
                    "➕ **افزودن اکانت** - اضافه کردن اکانت‌های تلگرام\n"
                    "📋 **مدیریت اکانت‌ها** - مشاهده لیست اکانت‌ها\n"
                    "🔗 **جوین کانال** - عضویت در کانال/گروه\n"
                    "🚪 **لفت کانال** - خروج از کانال/گروه\n"
                    "🤖 **استارت رفرال** - استارت ربات با لینک رفرال\n"
                    "💬 **ارسال پیام** - ارسال پیام به کاربر\n"
                    "❤️ **ری‌اکشن و سین** - ری‌اکشن و سین زدن پست‌ها\n"
                    "🚫 **بلاک/انبلاک** - بلاک یا انبلاک کردن کاربر\n"
                    "🎯 **سناریو پیشرفته** - اجرای سناریوهای پیچیده\n\n"
                    "از منوی زیر استفاده کنید:"
                )
            elif is_admin:
                # منوی کامل برای ادمین (بدون پنل ادمین)
                buttons = [
                    [Button.inline("➕ افزودن اکانت", b"add_account"),
                     Button.inline("📋 اکانت‌های من", b"my_accounts")],
                    [Button.inline("🔗 جوین کانال", b"join_channel"), 
                     Button.inline("🚪 لفت کانال", b"leave_channel")],
                    [Button.inline("🤖 استارت رفرال", b"start_referral"),
                     Button.inline("💬 ارسال پیام", b"send_message")],
                    [Button.inline("❤️ ری‌اکشن و سین", b"react_post"),
                     Button.inline("🚫 بلاک/انبلاک", b"block_user")],
                    [Button.inline("🎯 سناریو پیشرفته", b"advanced_scenario")],
                    [Button.inline("⚙️ مدیریت ربات", b"bot_management")]
                ]
                
                welcome_text = (
                    "🔐 **ربات مدیریت اکانت تلگرام**\n\n"
                    "👨‍💼 **شما ادمین هستید**\n\n"
                    "به ربات خوش آمدید! این ربات می‌تواند:\n\n"
                    "➕ **افزودن اکانت** - اضافه کردن اکانت‌های تلگرام\n"
                    "📋 **مدیریت اکانت‌ها** - مشاهده لیست اکانت‌ها\n"
                    "🔗 **جوین کانال** - عضویت در کانال/گروه\n"
                    "🚪 **لفت کانال** - خروج از کانال/گروه\n"
                    "🤖 **استارت رفرال** - استارت ربات با لینک رفرال\n"
                    "💬 **ارسال پیام** - ارسال پیام به کاربر\n"
                    "❤️ **ری‌اکشن و سین** - ری‌اکشن و سین زدن پست‌ها\n"
                    "🚫 **بلاک/انبلاک** - بلاک یا انبلاک کردن کاربر\n"
                    "🎯 **سناریو پیشرفته** - اجرای سناریوهای پیچیده\n\n"
                    "از منوی زیر استفاده کنید:"
                )
            else:
                # منوی محدود برای کاربران عادی (فقط افزودن اکانت)
                buttons = [
                    [Button.inline("➕ افزودن اکانت", b"add_account")]
                ]
                
                welcome_text = (
                    "🔐 **ربات مدیریت اکانت تلگرام**\n\n"
                    "به ربات خوش آمدید!\n\n"
                    "شما می‌توانید اکانت‌های تلگرام را به ربات اضافه کنید.\n\n"
                    "➕ **افزودن اکانت** - اضافه کردن اکانت جدید\n\n"
                    "💡 اکانت‌هایی که اضافه می‌کنید برای ادمین اصلی ثبت می‌شوند.\n\n"
                    "⚠️ برای دسترسی به قابلیت‌های بیشتر، با ادمین تماس بگیرید."
                )
            
            await event.respond(welcome_text, buttons=buttons)
        
        @self.bot.on(events.CallbackQuery(pattern=b"add_account"))
        async def add_account_callback(event):
            """شروع فرآیند افزودن اکانت"""
            await event.answer()
            
            # تعیین اینکه اکانت برای کی اضافه میشه
            user_id = event.sender_id
            is_creator = user_id in Config.ADMIN_IDS
            is_admin = await self.db.is_admin(user_id)
            
            # بررسی تایید کاربر
            if not is_creator and not is_admin:
                user = await self.db.get_user(user_id)
                if not user or not user.is_approved:
                    await event.edit(
                        "⏳ **در انتظار تایید**\n\n"
                        "شما هنوز تایید نشده‌اید.\n\n"
                        "لطفاً منتظر تایید سازنده باشید.",
                        buttons=Button.inline("🔙 بازگشت", b"back_to_menu")
                    )
                    return
            
            if is_creator or is_admin:
                # ادمین‌ها برای خودشون اکانت اضافه می‌کنن
                target_user_id = user_id
                message = (
                    "📱 **افزودن اکانت**\n\n"
                    "شماره تلفن خود را ارسال کنید.\n"
                    "مثال: +989123456789\n\n"
                    "💡 این اکانت برای شما ثبت می‌شود."
                )
            else:
                # کاربران عادی برای ادمین اصلی اکانت اضافه می‌کنن
                target_user_id = Config.ADMIN_IDS[0]
                message = (
                    "📱 **افزودن اکانت**\n\n"
                    "شماره تلفن را ارسال کنید.\n"
                    "مثال: +989123456789\n\n"
                    "💡 این اکانت برای ادمین اصلی ثبت می‌شود."
                )
            
            await event.edit(
                message,
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {
                'step': 'phone',
                'target_user_id': target_user_id
            }
        
        @self.bot.on(events.CallbackQuery(pattern=b"my_accounts"))
        async def my_accounts_callback(event):
            """نمایش اکانت‌های کاربر"""
            await event.answer()
            
            user_id = event.sender_id
            is_creator = user_id in Config.ADMIN_IDS
            is_admin = await self.db.is_admin(user_id)
            
            # فقط سازنده و ادمین‌ها می‌تونن اکانت‌ها رو ببینن
            if not is_creator and not is_admin:
                await event.edit(
                    "⛔️ **دسترسی محدود**\n\n"
                    "شما فقط می‌توانید اکانت اضافه کنید.\n"
                    "برای مشاهده اکانت‌ها نیاز به دسترسی ادمین دارید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            # سازنده و ادمین‌ها فقط اکانت‌های خودشون رو می‌بینن
            accounts = await self.db.get_accounts(user_id)
            
            if is_creator:
                title = "📋 **اکانت‌های شما (سازنده):**\n\n"
            else:
                title = "📋 **اکانت‌های شما (ادمین):**\n\n"
            
            if not accounts:
                await event.edit(
                    "❌ هنوز اکانتی اضافه نشده است.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            text = title
            for i, acc in enumerate(accounts, 1):
                status_emoji = "✅" if acc.status == "active" else "❌"
                text += f"{i}. {status_emoji} {acc.phone}\n"
                text += f"   👤 @{acc.telegram_username or 'ندارد'}\n"
                text += f"   📅 {acc.created_at[:10]}\n\n"
            
            await event.edit(
                text,
                buttons=[
                    [Button.inline("➕ افزودن اکانت", b"add_account")],
                    [Button.inline("🔙 بازگشت", b"back_to_menu")]
                ]
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_panel"))
        async def admin_panel_callback(event):
            """پنل ادمین"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            
            buttons = [
                [Button.inline("📊 آمار کلی", b"admin_stats")],
                [Button.inline("👥 لیست کاربران", b"admin_users")],
                [Button.inline("📱 همه اکانت‌ها", b"admin_accounts")],
                [Button.inline("⏳ کاربران در انتظار", b"admin_pending")],
                [Button.inline("👑 مدیریت ادمین‌ها", b"admin_manage")],
                [Button.inline("💾 بکاپ کامل", b"admin_backup")],
                [Button.inline("📥 ریستور بکاپ", b"admin_restore")],
                [Button.inline("⚙️ تنظیم کانال بکاپ", b"admin_set_backup_channel")],
                [Button.inline("🔙 بازگشت", b"back_to_menu")]
            ]
            
            await event.edit(
                "👑 **پنل مدیریت**\n\n"
                "از منوی زیر استفاده کنید:",
                buttons=buttons
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_stats"))
        async def admin_stats_callback(event):
            """نمایش آمار"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            stats = await self.db.get_stats()
            
            text = "📊 **آمار کلی ربات**\n\n"
            text += f"👥 تعداد کاربران: {stats['total_users']}\n"
            text += f"📱 تعداد اکانت‌ها: {stats['total_accounts']}\n"
            text += f"✅ اکانت‌های فعال: {stats['active_accounts']}\n\n"
            
            if stats['recent_accounts']:
                text += "📋 **آخرین اکانت‌ها:**\n"
                for phone, created_at in stats['recent_accounts']:
                    text += f"• {phone} - {created_at[:10]}\n"
            
            await event.edit(
                text,
                buttons=Button.inline("🔙 بازگشت", b"admin_panel")
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_accounts"))
        async def admin_accounts_callback(event):
            """نمایش همه اکانت‌ها"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            accounts = await self.db.get_accounts()
            
            if not accounts:
                await event.edit(
                    "❌ هنوز اکانتی ثبت نشده است.",
                    buttons=Button.inline("🔙 بازگشت", b"admin_panel")
                )
                return
            
            text = "📱 **همه اکانت‌ها:**\n\n"
            for i, acc in enumerate(accounts[:20], 1):  # نمایش 20 اکانت اول
                status_emoji = "✅" if acc.status == "active" else "❌"
                text += f"{i}. {status_emoji} {acc.phone}\n"
                text += f"   👤 @{acc.telegram_username or 'ندارد'}\n"
                text += f"   🆔 مالک: {acc.user_id}\n"
                
                # نمایش کسی که اضافه کرده
                if acc.added_by:
                    if acc.added_by == acc.user_id:
                        text += f"   ➕ توسط خودش اضافه شده\n"
                    else:
                        text += f"   ➕ اضافه شده توسط: {acc.added_by}\n"
                
                text += "\n"
            
            if len(accounts) > 20:
                text += f"... و {len(accounts) - 20} اکانت دیگر"
            
            await event.edit(
                text,
                buttons=Button.inline("🔙 بازگشت", b"admin_panel")
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_manage"))
        async def admin_manage_callback(event):
            """مدیریت ادمین‌ها"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            
            # دریافت لیست ادمین‌ها
            admins = await self.db.get_all_admins()
            
            text = "👑 **مدیریت ادمین‌ها**\n\n"
            text += "📋 **لیست ادمین‌های فعلی:**\n\n"
            
            for admin in admins:
                name = admin.first_name or admin.username or str(admin.user_id)
                text += f"• {name} (`{admin.user_id}`)\n"
            
            text += "\n💡 **دستورات:**\n"
            text += "• برای اضافه کردن ادمین: `/addadmin USER_ID`\n"
            text += "• برای حذف ادمین: `/removeadmin USER_ID`\n\n"
            text += "مثال: `/addadmin 123456789`"
            
            await event.edit(
                text,
                buttons=Button.inline("🔙 بازگشت", b"admin_panel")
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_pending"))
        async def admin_pending_callback(event):
            """نمایش کاربران در انتظار تایید"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            
            # دریافت کاربران در انتظار
            pending_users = await self.db.get_pending_users()
            
            if not pending_users:
                await event.edit(
                    "✅ **هیچ کاربری در انتظار تایید نیست!**",
                    buttons=Button.inline("🔙 بازگشت", b"admin_panel")
                )
                return
            
            text = "⏳ **کاربران در انتظار تایید:**\n\n"
            
            for i, user in enumerate(pending_users[:10], 1):
                text += f"{i}. 👤 {user.first_name or 'ندارد'}\n"
                text += f"   🆔 یوزرنیم: @{user.username or 'ندارد'}\n"
                text += f"   🔢 آیدی: `{user.user_id}`\n"
                text += f"   📅 تاریخ: {user.created_at[:10] if user.created_at else 'نامشخص'}\n\n"
            
            if len(pending_users) > 10:
                text += f"... و {len(pending_users) - 10} کاربر دیگر\n\n"
            
            text += "\n💡 **برای تایید:** `/approve USER_ID`\n"
            text += "💡 **برای رد:** `/reject USER_ID`"
            
            await event.edit(
                text,
                buttons=Button.inline("🔙 بازگشت", b"admin_panel")
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"approve_"))
        async def approve_callback(event):
            """تایید دسترسی کاربر از طریق دکمه"""
            # فقط سازنده دسترسی داره
            if event.sender_id not in Config.ADMIN_IDS:
                await event.answer("⛔️ شما دسترسی ندارید!", alert=True)
                return
            
            # دریافت user_id از callback data
            user_id = int(event.data.decode().split('_')[1])
            
            # تایید کاربر
            success = await self.db.approve_user(user_id)
            
            if success:
                await event.edit(
                    f"✅ **کاربر تایید شد!**\n\n"
                    f"🆔 آیدی: `{user_id}`\n\n"
                    f"این کاربر حالا می‌تواند از ربات استفاده کند."
                )
                
                # اطلاع به کاربر
                try:
                    await self.bot.send_message(
                        user_id,
                        "✅ **دسترسی شما تایید شد!**\n\n"
                        "حالا می‌توانید از ربات استفاده کنید.\n\n"
                        "برای شروع /start را ارسال کنید."
                    )
                except:
                    pass
                
                await self.db.log_action('approve_user', event.sender_id, str(user_id))
            else:
                await event.answer("❌ خطا در تایید کاربر!", alert=True)
        
        @self.bot.on(events.CallbackQuery(pattern=b"reject_"))
        async def reject_callback(event):
            """رد دسترسی کاربر از طریق دکمه"""
            # فقط سازنده دسترسی داره
            if event.sender_id not in Config.ADMIN_IDS:
                await event.answer("⛔️ شما دسترسی ندارید!", alert=True)
                return
            
            # دریافت user_id از callback data
            user_id = int(event.data.decode().split('_')[1])
            
            await event.edit(
                f"❌ **درخواست رد شد**\n\n"
                f"🆔 آیدی: `{user_id}`\n\n"
                f"این کاربر نمی‌تواند از ربات استفاده کند."
            )
            
            # اطلاع به کاربر
            try:
                await self.bot.send_message(
                    user_id,
                    "❌ **درخواست شما رد شد**\n\n"
                    "متأسفانه نمی‌توانید از این ربات استفاده کنید."
                )
            except:
                pass
            
            await self.db.log_action('reject_user', event.sender_id, str(user_id))
        
        @self.bot.on(events.NewMessage(pattern='/approve'))
        async def approve_command_handler(event):
            """تایید دسترسی کاربر با دستور"""
            # فقط سازنده می‌تونه تایید کنه
            if event.sender_id not in Config.ADMIN_IDS:
                await event.respond("⛔️ فقط سازنده می‌تواند کاربر تایید کند!")
                return
            
            try:
                # دریافت آیدی کاربر
                parts = event.message.text.split()
                if len(parts) < 2:
                    await event.respond(
                        "❌ فرمت نادرست!\n\n"
                        "استفاده: `/approve USER_ID`\n"
                        "مثال: `/approve 123456789`"
                    )
                    return
                
                user_id = int(parts[1])
                
                # تایید کاربر
                success = await self.db.approve_user(user_id)
                
                if success:
                    await event.respond(
                        f"✅ **کاربر تایید شد!**\n\n"
                        f"🆔 آیدی: `{user_id}`\n\n"
                        f"این کاربر حالا می‌تواند از ربات استفاده کند."
                    )
                    
                    # اطلاع به کاربر
                    try:
                        await self.bot.send_message(
                            user_id,
                            "✅ **دسترسی شما تایید شد!**\n\n"
                            "حالا می‌توانید از ربات استفاده کنید.\n\n"
                            "برای شروع /start را ارسال کنید."
                        )
                    except:
                        pass
                    
                    await self.db.log_action('approve_user', event.sender_id, str(user_id))
                else:
                    await event.respond("❌ خطا در تایید کاربر!")
                    
            except ValueError:
                await event.respond("❌ آیدی نامعتبر است! لطفاً یک عدد صحیح وارد کنید.")
            except Exception as e:
                await event.respond(f"❌ خطا: {str(e)}")
        
        @self.bot.on(events.NewMessage(pattern='/reject'))
        async def reject_command_handler(event):
            """رد دسترسی کاربر با دستور"""
            # فقط سازنده می‌تونه رد کنه
            if event.sender_id not in Config.ADMIN_IDS:
                await event.respond("⛔️ فقط سازنده می‌تواند کاربر رد کند!")
                return
            
            try:
                # دریافت آیدی کاربر
                parts = event.message.text.split()
                if len(parts) < 2:
                    await event.respond(
                        "❌ فرمت نادرست!\n\n"
                        "استفاده: `/reject USER_ID`\n"
                        "مثال: `/reject 123456789`"
                    )
                    return
                
                user_id = int(parts[1])
                
                await event.respond(
                    f"❌ **درخواست رد شد**\n\n"
                    f"🆔 آیدی: `{user_id}`\n\n"
                    f"این کاربر نمی‌تواند از ربات استفاده کند."
                )
                
                # اطلاع به کاربر
                try:
                    await self.bot.send_message(
                        user_id,
                        "❌ **درخواست شما رد شد**\n\n"
                        "متأسفانه نمی‌توانید از این ربات استفاده کنید."
                    )
                except:
                    pass
                
                await self.db.log_action('reject_user', event.sender_id, str(user_id))
                    
            except ValueError:
                await event.respond("❌ آیدی نامعتبر است! لطفاً یک عدد صحیح وارد کنید.")
            except Exception as e:
                await event.respond(f"❌ خطا: {str(e)}")
        
        @self.bot.on(events.NewMessage(pattern='/addadmin'))
        async def add_admin_handler(event):
            """اضافه کردن ادمین"""
            # فقط سازنده می‌تونه ادمین اضافه کنه
            if event.sender_id not in Config.ADMIN_IDS:
                await event.respond("⛔️ فقط سازنده می‌تواند ادمین اضافه کند!")
                return
            
            try:
                # دریافت آیدی کاربر
                parts = event.message.text.split()
                if len(parts) < 2:
                    await event.respond(
                        "❌ فرمت نادرست!\n\n"
                        "استفاده: `/addadmin USER_ID`\n"
                        "مثال: `/addadmin 123456789`"
                    )
                    return
                
                new_admin_id = int(parts[1])
                
                # اضافه کردن به دیتابیس
                success = await self.db.add_admin(new_admin_id)
                
                if success:
                    await event.respond(
                        f"✅ **ادمین اضافه شد!**\n\n"
                        f"🆔 آیدی: `{new_admin_id}`\n\n"
                        f"این کاربر حالا به تمام قابلیت‌های ربات دسترسی دارد."
                    )
                    await self.db.log_action('add_admin', event.sender_id, str(new_admin_id))
                else:
                    await event.respond("❌ خطا در اضافه کردن ادمین!")
                    
            except ValueError:
                await event.respond("❌ آیدی نامعتبر است! لطفاً یک عدد صحیح وارد کنید.")
            except Exception as e:
                await event.respond(f"❌ خطا: {str(e)}")
        
        @self.bot.on(events.NewMessage(pattern='/removeadmin'))
        async def remove_admin_handler(event):
            """حذف ادمین"""
            # فقط سازنده می‌تونه ادمین حذف کنه
            if event.sender_id not in Config.ADMIN_IDS:
                await event.respond("⛔️ فقط سازنده می‌تواند ادمین حذف کند!")
                return
            
            try:
                # دریافت آیدی کاربر
                parts = event.message.text.split()
                if len(parts) < 2:
                    await event.respond(
                        "❌ فرمت نادرست!\n\n"
                        "استفاده: `/removeadmin USER_ID`\n"
                        "مثال: `/removeadmin 123456789`"
                    )
                    return
                
                admin_id = int(parts[1])
                
                # جلوگیری از حذف سازنده
                if admin_id in Config.ADMIN_IDS:
                    await event.respond("❌ نمی‌توانید سازنده را حذف کنید!")
                    return
                
                # حذف از دیتابیس
                success = await self.db.remove_admin(admin_id)
                
                if success:
                    await event.respond(
                        f"✅ **ادمین حذف شد!**\n\n"
                        f"🆔 آیدی: `{admin_id}`\n\n"
                        f"این کاربر دیگر دسترسی ادمین ندارد."
                    )
                    await self.db.log_action('remove_admin', event.sender_id, str(admin_id))
                else:
                    await event.respond("❌ خطا در حذف ادمین!")
                    
            except ValueError:
                await event.respond("❌ آیدی نامعتبر است! لطفاً یک عدد صحیح وارد کنید.")
            except Exception as e:
                await event.respond(f"❌ خطا: {str(e)}")
        
        @self.bot.on(events.CallbackQuery(pattern=b"join_channel"))
        async def join_channel_callback(event):
            """شروع فرآیند جوین کانال"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            accounts = await self.db.get_accounts(event.sender_id)
            
            if not accounts:
                await event.edit(
                    "❌ شما هنوز اکانتی اضافه نکرده‌اید.\n"
                    "ابتدا یک اکانت اضافه کنید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            await event.edit(
                "🔗 **جوین کانال/گروه**\n\n"
                "لینک کانال یا گروه را ارسال کنید:\n\n"
                "✅ لینک عمومی: https://t.me/channel\n"
                "✅ لینک خصوصی: https://t.me/+hash\n"
                "✅ یوزرنیم: @channel یا channel",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'join_link'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"leave_channel"))
        async def leave_channel_callback(event):
            """شروع فرآیند لفت کانال"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            accounts = await self.db.get_accounts(event.sender_id)
            
            if not accounts:
                await event.edit(
                    "❌ شما هنوز اکانتی اضافه نکرده‌اید.\n"
                    "ابتدا یک اکانت اضافه کنید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            await event.edit(
                "🚪 **لفت کانال/گروه**\n\n"
                "لینک یا یوزرنیم کانال/گروه را ارسال کنید:\n\n"
                "✅ لینک: https://t.me/channel\n"
                "✅ یوزرنیم: @channel یا channel",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'leave_link'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"start_referral"))
        async def start_referral_callback(event):
            """شروع فرآیند استارت رفرال"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            accounts = await self.db.get_accounts(event.sender_id)
            
            if not accounts:
                await event.edit(
                    "❌ شما هنوز اکانتی اضافه نکرده‌اید.\n"
                    "ابتدا یک اکانت اضافه کنید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            await event.edit(
                "🤖 **استارت ربات با رفرال**\n\n"
                "لینک رفرال ربات را ارسال کنید:\n\n"
                "✅ فرمت 1: https://t.me/bot_name?start=ref_id\n"
                "✅ فرمت 2: @bot_name ref_id\n\n"
                "مثال:\n"
                "https://t.me/amxvpn_bot?start=631388884\n"
                "یا\n"
                "@amxvpn_bot 631388884",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'referral_link'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"send_message"))
        async def send_message_callback(event):
            """شروع فرآیند ارسال پیام"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            accounts = await self.db.get_accounts(event.sender_id)
            
            if not accounts:
                await event.edit(
                    "❌ شما هنوز اکانتی اضافه نکرده‌اید.\n"
                    "ابتدا یک اکانت اضافه کنید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            await event.edit(
                "💬 **ارسال پیام**\n\n"
                "یوزرنیم یا آیدی عددی کاربر مقصد را ارسال کنید:\n\n"
                "✅ یوزرنیم: @username یا username\n"
                "✅ آیدی عددی: 123456789\n\n"
                "مثال:\n"
                "@john_doe\n"
                "یا\n"
                "631388884",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'message_target'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"react_post"))
        async def react_post_callback(event):
            """شروع فرآیند ری‌اکشن و سین"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            accounts = await self.db.get_accounts(event.sender_id)
            
            if not accounts:
                await event.edit(
                    "❌ شما هنوز اکانتی اضافه نکرده‌اید.\n"
                    "ابتدا یک اکانت اضافه کنید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            await event.edit(
                "❤️ **ری‌اکشن و سین زدن پست**\n\n"
                "لینک پست کانال را ارسال کنید:\n\n"
                "✅ فرمت: https://t.me/channel/123\n"
                "✅ یا: https://t.me/c/1234567890/123\n\n"
                "💡 **نکات:**\n"
                "• هر اکانت یک ری‌اکشن تصادفی می‌زند\n"
                "• سین (view) پست هم زده می‌شود\n"
                "• همه اکانت‌ها این کار را انجام می‌دهند\n\n"
                "مثال:\n"
                "https://t.me/mychannel/456",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'react_link'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"block_user"))
        async def block_user_callback(event):
            """منوی بلاک/انبلاک"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            accounts = await self.db.get_accounts(event.sender_id)
            
            if not accounts:
                await event.edit(
                    "❌ شما هنوز اکانتی اضافه نکرده‌اید.\n"
                    "ابتدا یک اکانت اضافه کنید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            await event.edit(
                "🚫 **بلاک/انبلاک کاربر**\n\n"
                "چه کاری میخواهید انجام دهید؟",
                buttons=[
                    [Button.inline("🚫 بلاک کردن", b"do_block")],
                    [Button.inline("✅ انبلاک کردن", b"do_unblock")],
                    [Button.inline("🔙 بازگشت", b"back_to_menu")]
                ]
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"do_block"))
        async def do_block_callback(event):
            """شروع فرآیند بلاک"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            await event.edit(
                "🚫 **بلاک کردن کاربر**\n\n"
                "یوزرنیم یا آیدی عددی کاربر را ارسال کنید:\n\n"
                "✅ یوزرنیم: @username یا username\n"
                "✅ آیدی عددی: 123456789\n\n"
                "💡 **نکته:** این کاربر توسط همه اکانت‌های شما بلاک می‌شود.\n\n"
                "مثال:\n"
                "@spammer\n"
                "یا\n"
                "123456789",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'block_target'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"do_unblock"))
        async def do_unblock_callback(event):
            """شروع فرآیند انبلاک"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            await event.edit(
                "✅ **انبلاک کردن کاربر**\n\n"
                "یوزرنیم یا آیدی عددی کاربر را ارسال کنید:\n\n"
                "✅ یوزرنیم: @username یا username\n"
                "✅ آیدی عددی: 123456789\n\n"
                "💡 **نکته:** این کاربر توسط همه اکانت‌های شما انبلاک می‌شود.\n\n"
                "مثال:\n"
                "@someone\n"
                "یا\n"
                "123456789",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'unblock_target'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"bot_management"))
        async def bot_management_callback(event):
            """منوی مدیریت ربات"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            # دریافت آمار
            accounts = await self.db.get_accounts(event.sender_id)
            active_count = len([acc for acc in accounts if acc.status == 'active'])
            
            buttons = [
                [Button.inline("🔄 تنظیمات تایمر", b"timer_settings")],
                [Button.inline("📊 آمار من", b"my_stats")],
                [Button.inline("❓ راهنما", b"help")],
                [Button.inline("🔙 بازگشت", b"back_to_menu")]
            ]
            
            await event.edit(
                f"⚙️ **مدیریت ربات**\n\n"
                f"📱 تعداد اکانت‌ها: {len(accounts)}\n"
                f"✅ اکانت‌های فعال: {active_count}\n"
                f"⏱ تاخیر فعلی: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                f"از منوی زیر استفاده کنید:",
                buttons=buttons
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"timer_settings"))
        async def timer_settings_callback(event):
            """تنظیمات تایمر"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            await event.edit(
                f"⏱ **تنظیمات تایمر**\n\n"
                f"تاخیر فعلی: {Config.DELAY_BETWEEN_ACTIONS} ثانیه\n"
                f"محدوده تصادفی: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                f"💡 **توضیحات:**\n"
                f"• تاخیر بین هر عملیات برای جلوگیری از فلود\n"
                f"• محدوده تصادفی برای طبیعی‌تر بودن\n"
                f"• تنظیمات فعلی ایمن و بهینه است\n\n"
                f"⚠️ برای تغییر تنظیمات، فایل .env را ویرایش کنید:\n"
                f"DELAY_BETWEEN_ACTIONS=5\n"
                f"DELAY_RANDOM_RANGE=3",
                buttons=Button.inline("🔙 بازگشت", b"bot_management")
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"my_stats"))
        async def my_stats_callback(event):
            """آمار کاربر"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            # دریافت آمار از دیتابیس
            accounts = await self.db.get_accounts(event.sender_id)
            
            active_count = len([acc for acc in accounts if acc.status == 'active'])
            inactive_count = len(accounts) - active_count
            
            # آخرین فعالیت‌ها
            stats_text = f"📊 **آمار شما**\n\n"
            stats_text += f"📱 کل اکانت‌ها: {len(accounts)}\n"
            stats_text += f"✅ فعال: {active_count}\n"
            stats_text += f"❌ غیرفعال: {inactive_count}\n\n"
            
            if accounts:
                stats_text += "📋 **آخرین اکانت‌ها:**\n"
                for acc in accounts[:5]:
                    status = "✅" if acc.status == "active" else "❌"
                    stats_text += f"{status} {acc.phone} - {acc.created_at[:10]}\n"
            
            await event.edit(
                stats_text,
                buttons=Button.inline("🔙 بازگشت", b"bot_management")
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"help"))
        async def help_callback(event):
            """راهنما"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            help_text = (
                "❓ **راهنمای استفاده**\n\n"
                "**➕ افزودن اکانت:**\n"
                "شماره → کد تایید → رمز (اختیاری)\n\n"
                "**🔗 جوین کانال:**\n"
                "لینک کانال/گروه → جوین خودکار\n\n"
                "**🚪 لفت کانال:**\n"
                "یوزرنیم کانال → لفت خودکار\n\n"
                "**🤖 استارت رفرال:**\n"
                "لینک رفرال → کلمه کلیدی دکمه (اختیاری) → استارت خودکار\n\n"
                "**💬 ارسال پیام:**\n"
                "یوزرنیم/آیدی → متن پیام → ارسال خودکار\n\n"
                "💡 **نکات:**\n"
                "• همه عملیات با تایمر و تاخیر انجام می‌شود\n"
                "• برای جلوگیری از بن، تنظیمات را تغییر ندهید\n"
                "• اکانت‌های خود را به صورت دوره‌ای چک کنید"
            )
            
            await event.edit(
                help_text,
                buttons=Button.inline("🔙 بازگشت", b"bot_management")
            )
        
        @self.bot.on(events.CallbackQuery(pattern=b"cancel|back_to_menu"))
        async def cancel_callback(event):
            """لغو عملیات"""
            await event.answer()
            
            # لغو فرآیند ورود اگر در حال انجام است
            if event.sender_id in self.user_states:
                await self.receiver.cancel_login(event.sender_id)
                del self.user_states[event.sender_id]
            
            # بازگشت به منوی اصلی
            user = await event.get_sender()
            
            # بررسی دسترسی کاربر
            is_creator = user.id in Config.ADMIN_IDS
            is_admin = await self.db.is_admin(user.id)
            
            if is_creator:
                # منوی کامل برای سازنده
                buttons = [
                    [Button.inline("➕ افزودن اکانت", b"add_account"),
                     Button.inline("📋 اکانت‌های من", b"my_accounts")],
                    [Button.inline("🔗 جوین کانال", b"join_channel"), 
                     Button.inline("🚪 لفت کانال", b"leave_channel")],
                    [Button.inline("🤖 استارت رفرال", b"start_referral"),
                     Button.inline("💬 ارسال پیام", b"send_message")],
                    [Button.inline("❤️ ری‌اکشن و سین", b"react_post"),
                     Button.inline("🚫 بلاک/انبلاک", b"block_user")],
                    [Button.inline("🎯 سناریو پیشرفته", b"advanced_scenario")],
                    [Button.inline("⚙️ مدیریت ربات", b"bot_management")],
                    [Button.inline("👑 پنل ادمین", b"admin_panel")]
                ]
            elif is_admin:
                # منوی کامل برای ادمین (بدون پنل ادمین)
                buttons = [
                    [Button.inline("➕ افزودن اکانت", b"add_account"),
                     Button.inline("📋 اکانت‌های من", b"my_accounts")],
                    [Button.inline("🔗 جوین کانال", b"join_channel"), 
                     Button.inline("🚪 لفت کانال", b"leave_channel")],
                    [Button.inline("🤖 استارت رفرال", b"start_referral"),
                     Button.inline("💬 ارسال پیام", b"send_message")],
                    [Button.inline("❤️ ری‌اکشن و سین", b"react_post"),
                     Button.inline("🚫 بلاک/انبلاک", b"block_user")],
                    [Button.inline("🎯 سناریو پیشرفته", b"advanced_scenario")],
                    [Button.inline("⚙️ مدیریت ربات", b"bot_management")]
                ]
            else:
                # منوی محدود برای کاربران عادی (فقط افزودن اکانت)
                buttons = [
                    [Button.inline("➕ افزودن اکانت", b"add_account")]
                ]
            
            await event.edit(
                "🔐 **منوی اصلی**",
                buttons=buttons
            )
        
        @self.bot.on(events.NewMessage(pattern='/cancel'))
        async def cancel_handler(event):
            """هندلر لغو عملیات"""
            if event.sender_id in self.user_states:
                await self.receiver.cancel_login(event.sender_id)
                del self.user_states[event.sender_id]
            await event.respond("❌ عملیات لغو شد.")
        
        @self.bot.on(events.NewMessage(func=lambda e: not e.message.text.startswith('/')))
        async def message_handler(event):
            """هندلر پیام‌های عادی"""
            user_id = event.sender_id
            
            if user_id not in self.user_states:
                return
            
            state = self.user_states[user_id]
            step = state.get('step')
            
            if step == 'phone':
                # دریافت شماره تلفن
                phone = event.message.text.strip()
                
                # ارسال درخواست کد
                await event.respond("⏳ در حال ارسال کد تایید...")
                
                result = await self.receiver.send_code_request(phone, user_id)
                
                if result['success']:
                    state['phone'] = phone
                    state['step'] = 'code'
                    await event.respond(
                        f"✅ کد تایید به شماره `{phone}` ارسال شد.\n\n"
                        "لطفاً کد 5 رقمی را ارسال کنید:",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
                    await self.db.log_action('code_sent', user_id, phone)
                else:
                    await event.respond(
                        f"❌ خطا: {result['message']}",
                        buttons=[
                            [Button.inline("🔄 تلاش مجدد", b"add_account")],
                            [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                        ]
                    )
                    del self.user_states[user_id]
            
            elif step == 'code':
                # دریافت کد تایید
                code_text = event.message.text.strip()
                
                # استخراج کد از متن (اگر کل پیام تلگرام رو کپی کرده)
                code = extract_telegram_code(code_text)
                
                if not code:
                    # اگر استخراج نشد، خود متن رو به عنوان کد در نظر بگیر
                    code = code_text
                
                await event.respond("⏳ در حال بررسی کد...")
                
                result = await self.receiver.sign_in_with_code(
                    user_id=user_id,
                    phone=state['phone'],
                    code=code
                )
                
                if result.get('need_restart'):
                    # نیاز به شروع مجدد
                    await event.respond(
                        f"❌ {result['message']}",
                        buttons=[
                            [Button.inline("🔄 شروع مجدد", b"add_account")],
                            [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                        ]
                    )
                    del self.user_states[user_id]
                
                elif result.get('need_password'):
                    # نیاز به رمز دو مرحله‌ای
                    state['step'] = 'password'
                    await event.respond(
                        "🔐 **رمز دو مرحله‌ای مورد نیاز است**\n\n"
                        "لطفاً رمز عبور خود را ارسال کنید:",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
                
                elif result.get('completed'):
                    # ورود موفق
                    target_user_id = state.get('target_user_id', user_id)
                    
                    account = Account(
                        user_id=target_user_id,  # ذخیره برای کاربر هدف
                        phone=state['phone'],
                        telegram_user_id=result['user_id'],
                        telegram_username=result.get('username'),
                        session_path=result['session_path'],
                        status='active',
                        added_by=user_id  # کسی که اکانت رو اضافه کرده
                    )
                    await self.db.add_account(account)
                    await self.db.log_action('account_added', user_id, f"{state['phone']} -> user:{target_user_id}")
                    
                    # آپلود سشن به کانال بکاپ (اگر تنظیم شده باشد)
                    if self.backup_manager.backup_channel_id:
                        asyncio.create_task(
                            self.backup_manager.upload_session_to_channel(
                                result['session_path'],
                                state['phone'],
                                result.get('username')
                            )
                        )
                    
                    # بازگشت به مرحله دریافت شماره برای اکانت بعدی
                    state['step'] = 'phone'
                    
                    # پیام متفاوت برای ادمین و کاربر عادی
                    if target_user_id == user_id:
                        success_msg = (
                            f"✅ **ورود موفق!**\n\n"
                            f"👤 نام: {result.get('first_name', 'نامشخص')}\n"
                            f"🆔 یوزرنیم: @{result.get('username') or 'ندارد'}\n"
                            f"📱 شماره: {state['phone']}\n"
                            f"📁 سشن ذخیره شد\n\n"
                            f"✨ **اکانت شما با موفقیت ثبت شد!**\n\n"
                            f"📱 برای افزودن اکانت بعدی، شماره تلفن را ارسال کنید.\n"
                            f"یا /cancel برای بازگشت به منوی اصلی."
                        )
                    else:
                        success_msg = (
                            f"✅ **ورود موفق!**\n\n"
                            f"👤 نام: {result.get('first_name', 'نامشخص')}\n"
                            f"🆔 یوزرنیم: @{result.get('username') or 'ندارد'}\n"
                            f"📱 شماره: {state['phone']}\n"
                            f"📁 سشن ذخیره شد\n\n"
                            f"✨ **اکانت برای ادمین اصلی ثبت شد!**\n\n"
                            f"📱 برای افزودن اکانت بعدی، شماره تلفن را ارسال کنید.\n"
                            f"یا /cancel برای بازگشت به منوی اصلی."
                        )
                    
                    await event.respond(
                        success_msg,
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                
                else:
                    # خطا
                    await event.respond(
                        f"❌ {result['message']}",
                        buttons=[
                            [Button.inline("🔄 تلاش مجدد", b"add_account")],
                            [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                        ]
                    )
                    await self.db.log_action('login_failed', user_id, result['message'])
            
            elif step == 'password':
                # دریافت رمز دو مرحله‌ای
                password = event.message.text.strip()
                
                await event.respond("⏳ در حال بررسی رمز...")
                
                result = await self.receiver.sign_in_with_password(
                    user_id=user_id,
                    password=password
                )
                
                if result.get('need_restart'):
                    # نیاز به شروع مجدد
                    await event.respond(
                        f"❌ {result['message']}",
                        buttons=[
                            [Button.inline("🔄 شروع مجدد", b"add_account")],
                            [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                        ]
                    )
                    del self.user_states[user_id]
                
                elif result.get('completed'):
                    # ورود موفق
                    target_user_id = state.get('target_user_id', user_id)
                    
                    account = Account(
                        user_id=target_user_id,  # ذخیره برای کاربر هدف
                        phone=state.get('phone', 'unknown'),
                        telegram_user_id=result['user_id'],
                        telegram_username=result.get('username'),
                        session_path=result['session_path'],
                        status='active',
                        added_by=user_id  # کسی که اکانت رو اضافه کرده
                    )
                    await self.db.add_account(account)
                    await self.db.log_action('account_added', user_id, f"{state.get('phone')} -> user:{target_user_id}")
                    
                    # آپلود سشن به کانال بکاپ (اگر تنظیم شده باشد)
                    if self.backup_manager.backup_channel_id:
                        asyncio.create_task(
                            self.backup_manager.upload_session_to_channel(
                                result['session_path'],
                                state.get('phone', 'unknown'),
                                result.get('username')
                            )
                        )
                    
                    # بازگشت به مرحله دریافت شماره برای اکانت بعدی
                    state['step'] = 'phone'
                    
                    # پیام متفاوت برای ادمین و کاربر عادی
                    if target_user_id == user_id:
                        success_msg = (
                            f"✅ **ورود موفق!**\n\n"
                            f"👤 نام: {result.get('first_name', 'نامشخص')}\n"
                            f"🆔 یوزرنیم: @{result.get('username') or 'ندارد'}\n"
                            f"📁 سشن ذخیره شد\n\n"
                            f"✨ **اکانت شما با موفقیت ثبت شد!**\n\n"
                            f"📱 برای افزودن اکانت بعدی، شماره تلفن را ارسال کنید.\n"
                            f"یا /cancel برای بازگشت به منوی اصلی."
                        )
                    else:
                        success_msg = (
                            f"✅ **ورود موفق!**\n\n"
                            f"👤 نام: {result.get('first_name', 'نامشخص')}\n"
                            f"🆔 یوزرنیم: @{result.get('username') or 'ندارد'}\n"
                            f"📁 سشن ذخیره شد\n\n"
                            f"✨ **اکانت برای ادمین اصلی ثبت شد!**\n\n"
                            f"📱 برای افزودن اکانت بعدی، شماره تلفن را ارسال کنید.\n"
                            f"یا /cancel برای بازگشت به منوی اصلی."
                        )
                    
                    await event.respond(
                        success_msg,
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                
                else:
                    # خطا
                    await event.respond(
                        f"❌ {result['message']}\n\n"
                        "لطفاً رمز صحیح را وارد کنید:",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
                    await self.db.log_action('password_failed', user_id, result['message'])

            elif step == 'join_link':
                # دریافت لینک برای جوین
                channel_link = event.message.text.strip()
                
                # دریافت اکانت‌های کاربر
                accounts = await self.db.get_accounts(user_id)
                active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                
                if not active_accounts:
                    await event.respond(
                        "❌ شما اکانت فعالی ندارید.",
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                    del self.user_states[user_id]
                    return
                
                # ذخیره اطلاعات و پرسیدن تعداد اکانت
                state['channel_link'] = channel_link
                state['active_accounts'] = active_accounts
                state['step'] = 'join_count'
                
                await event.respond(
                    f"📊 **انتخاب تعداد اکانت**\n\n"
                    f"شما {len(active_accounts)} اکانت فعال دارید.\n\n"
                    f"چند تا اکانت برای جوین استفاده شود؟\n\n"
                    f"💡 عدد ارسال کنید (مثلاً 5) یا:\n"
                    f"• /all برای همه اکانت‌ها",
                    buttons=Button.inline("❌ لغو", b"cancel")
                )
            
            elif step == 'join_count':
                # دریافت تعداد اکانت
                count_input = event.message.text.strip()
                
                active_accounts = state['active_accounts']
                channel_link = state['channel_link']
                
                # تعیین تعداد اکانت
                if count_input.lower() == '/all':
                    selected_accounts = active_accounts
                else:
                    try:
                        count = int(count_input)
                        if count <= 0:
                            await event.respond(
                                "❌ تعداد باید بیشتر از صفر باشد!",
                                buttons=Button.inline("❌ لغو", b"cancel")
                            )
                            return
                        selected_accounts = active_accounts[:min(count, len(active_accounts))]
                    except ValueError:
                        await event.respond(
                            "❌ لطفاً یک عدد معتبر یا /all ارسال کنید.",
                            buttons=Button.inline("❌ لغو", b"cancel")
                        )
                        return
                
                total = len(selected_accounts)
                
                # ارسال پیام شروع
                progress_msg = await event.respond(
                    f"⏳ **شروع عملیات جوین**\n\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"⏱ تاخیر بین هر عملیات: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید..."
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال جوین...**\n\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}"
                        )
                    except:
                        pass
                
                # جوین دسته‌جمعی با تایمر
                session_paths = [acc.session_path for acc in selected_accounts]
                results = await self.channel_manager.bulk_join(
                    session_paths,
                    channel_link,
                    progress_callback=update_progress
                )
                
                # نمایش نتایج
                results_text = "📊 **نتایج جوین:**\n\n"
                
                for i, detail in enumerate(results['details'][:10], 1):  # نمایش 10 مورد اول
                    phone_short = selected_accounts[i-1].phone[-4:] if selected_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        results_text += f"✅ {phone_short}: موفق\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                
                if len(results['details']) > 10:
                    results_text += f"\n... و {len(results['details']) - 10} مورد دیگر\n"
                
                results_text += f"\n✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("🔗 جوین مجدد", b"join_channel")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_join', user_id, f"{channel_link} - {results['success']}/{total}")
                del self.user_states[user_id]
            
            elif step == 'leave_link':
                # دریافت لینک برای لفت
                channel_link = event.message.text.strip()
                
                # دریافت اکانت‌های کاربر
                accounts = await self.db.get_accounts(user_id)
                active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                
                if not active_accounts:
                    await event.respond(
                        "❌ شما اکانت فعالی ندارید.",
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                    del self.user_states[user_id]
                    return
                
                # ذخیره اطلاعات و پرسیدن تعداد اکانت
                state['channel_link'] = channel_link
                state['active_accounts'] = active_accounts
                state['step'] = 'leave_count'
                
                await event.respond(
                    f"📊 **انتخاب تعداد اکانت**\n\n"
                    f"شما {len(active_accounts)} اکانت فعال دارید.\n\n"
                    f"چند تا اکانت برای لفت استفاده شود؟\n\n"
                    f"💡 عدد ارسال کنید (مثلاً 5) یا:\n"
                    f"• /all برای همه اکانت‌ها",
                    buttons=Button.inline("❌ لغو", b"cancel")
                )
            
            elif step == 'leave_count':
                # دریافت تعداد اکانت
                count_input = event.message.text.strip()
                
                active_accounts = state['active_accounts']
                channel_link = state['channel_link']
                
                # تعیین تعداد اکانت
                if count_input.lower() == '/all':
                    selected_accounts = active_accounts
                else:
                    try:
                        count = int(count_input)
                        if count <= 0:
                            await event.respond(
                                "❌ تعداد باید بیشتر از صفر باشد!",
                                buttons=Button.inline("❌ لغو", b"cancel")
                            )
                            return
                        selected_accounts = active_accounts[:min(count, len(active_accounts))]
                    except ValueError:
                        await event.respond(
                            "❌ لطفاً یک عدد معتبر یا /all ارسال کنید.",
                            buttons=Button.inline("❌ لغو", b"cancel")
                        )
                        return
                
                total = len(selected_accounts)
                
                # ارسال پیام شروع
                progress_msg = await event.respond(
                    f"⏳ **شروع عملیات لفت**\n\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"⏱ تاخیر بین هر عملیات: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید..."
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال لفت...**\n\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}"
                        )
                    except:
                        pass
                
                # لفت دسته‌جمعی با تایمر
                session_paths = [acc.session_path for acc in selected_accounts]
                results = await self.channel_manager.bulk_leave(
                    session_paths,
                    channel_link,
                    progress_callback=update_progress
                )
                
                # نمایش نتایج
                results_text = "📊 **نتایج لفت:**\n\n"
                
                for i, detail in enumerate(results['details'][:10], 1):  # نمایش 10 مورد اول
                    phone_short = selected_accounts[i-1].phone[-4:] if selected_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        results_text += f"✅ {phone_short}: موفق\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                
                if len(results['details']) > 10:
                    results_text += f"\n... و {len(results['details']) - 10} مورد دیگر\n"
                
                results_text += f"\n✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("🚪 لفت مجدد", b"leave_channel")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_leave', user_id, f"{channel_link} - {results['success']}/{total}")
                del self.user_states[user_id]

            elif step == 'referral_link':
                # دریافت لینک رفرال
                referral_input = event.message.text.strip()
                
                # تجزیه لینک رفرال
                parsed = self.referral_manager.parse_referral_link(referral_input)
                
                if 'error' in parsed:
                    await event.respond(
                        f"❌ {parsed['error']}\n\n"
                        "لطفاً لینک را به فرمت صحیح ارسال کنید:\n"
                        "https://t.me/bot_name?start=ref_id\n"
                        "یا\n"
                        "@bot_name ref_id",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
                    return
                
                bot_username = parsed['bot_username']
                start_param = parsed['start_param']
                
                # دریافت اکانت‌های کاربر
                accounts = await self.db.get_accounts(user_id)
                active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                
                if not active_accounts:
                    await event.respond(
                        "❌ شما اکانت فعالی ندارید.",
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                    del self.user_states[user_id]
                    return
                
                # ذخیره اطلاعات و پرسیدن تعداد اکانت
                state['bot_username'] = bot_username
                state['start_param'] = start_param
                state['active_accounts'] = active_accounts
                state['step'] = 'referral_count'
                
                await event.respond(
                    f"📊 **انتخاب تعداد اکانت**\n\n"
                    f"شما {len(active_accounts)} اکانت فعال دارید.\n\n"
                    f"چند تا اکانت برای استارت رفرال استفاده شود؟\n\n"
                    f"💡 عدد ارسال کنید (مثلاً 5) یا:\n"
                    f"• /all برای همه اکانت‌ها",
                    buttons=Button.inline("❌ لغو", b"cancel")
                )
            
            elif step == 'referral_count':
                # دریافت تعداد اکانت
                count_input = event.message.text.strip()
                
                active_accounts = state['active_accounts']
                bot_username = state['bot_username']
                start_param = state['start_param']
                
                # تعیین تعداد اکانت
                if count_input.lower() == '/all':
                    selected_accounts = active_accounts
                else:
                    try:
                        count = int(count_input)
                        if count <= 0:
                            await event.respond(
                                "❌ تعداد باید بیشتر از صفر باشد!",
                                buttons=Button.inline("❌ لغو", b"cancel")
                            )
                            return
                        selected_accounts = active_accounts[:min(count, len(active_accounts))]
                    except ValueError:
                        await event.respond(
                            "❌ لطفاً یک عدد معتبر یا /all ارسال کنید.",
                            buttons=Button.inline("❌ لغو", b"cancel")
                        )
                        return
                
                total = len(selected_accounts)
                
                # ارسال پیام شروع
                progress_msg = await event.respond(
                    f"⏳ **شروع عملیات استارت رفرال**\n\n"
                    f"🤖 ربات: @{bot_username}\n"
                    f"🔗 رفرال: {start_param}\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"⏱ تاخیر بین هر عملیات: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید..."
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال استارت...**\n\n"
                            f"🤖 ربات: @{bot_username}\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}"
                        )
                    except:
                        pass
                
                # استارت دسته‌جمعی با تایمر (بدون کلیک دکمه)
                session_paths = [acc.session_path for acc in selected_accounts]
                results = await self.referral_manager.bulk_start_bot(
                    session_paths,
                    bot_username,
                    start_param,
                    click_button=None,
                    progress_callback=update_progress
                )
                
                # نمایش نتایج
                results_text = "📊 **نتایج استارت رفرال:**\n\n"
                results_text += f"🤖 ربات: @{bot_username}\n"
                results_text += f"🔗 رفرال: {start_param}\n\n"
                
                for i, detail in enumerate(results['details'][:10], 1):  # نمایش 10 مورد اول
                    phone_short = selected_accounts[i-1].phone[-4:] if selected_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        results_text += f"✅ {phone_short}: موفق\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                
                if len(results['details']) > 10:
                    results_text += f"\n... و {len(results['details']) - 10} مورد دیگر\n"
                
                results_text += f"\n✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("🤖 استارت مجدد", b"start_referral")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_referral', user_id, f"@{bot_username} {start_param} - {results['success']}/{total}")
                del self.user_states[user_id]

            elif step == 'message_target':
                # دریافت یوزرنیم یا آیدی مقصد
                target = event.message.text.strip()
                
                state['target'] = target
                state['step'] = 'message_text'
                
                await event.respond(
                    f"💬 **ارسال پیام به: {target}**\n\n"
                    "حالا متن پیام خود را ارسال کنید:",
                    buttons=Button.inline("❌ لغو", b"cancel")
                )
            
            elif step == 'message_text':
                # دریافت متن پیام
                message_text = event.message.text.strip()
                target = state['target']
                
                # دریافت اکانت‌های کاربر
                accounts = await self.db.get_accounts(user_id)
                active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                
                if not active_accounts:
                    await event.respond(
                        "❌ شما اکانت فعالی ندارید.",
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                    del self.user_states[user_id]
                    return
                
                # ذخیره اطلاعات و پرسیدن تعداد اکانت
                state['message_text'] = message_text
                state['active_accounts'] = active_accounts
                state['step'] = 'message_count'
                
                await event.respond(
                    f"📊 **انتخاب تعداد اکانت**\n\n"
                    f"شما {len(active_accounts)} اکانت فعال دارید.\n\n"
                    f"چند تا اکانت برای ارسال پیام استفاده شود؟\n\n"
                    f"💡 عدد ارسال کنید (مثلاً 5) یا:\n"
                    f"• /all برای همه اکانت‌ها",
                    buttons=Button.inline("❌ لغو", b"cancel")
                )
            
            elif step == 'message_count':
                # دریافت تعداد اکانت
                count_input = event.message.text.strip()
                
                active_accounts = state['active_accounts']
                target = state['target']
                message_text = state['message_text']
                
                # تعیین تعداد اکانت
                if count_input.lower() == '/all':
                    selected_accounts = active_accounts
                else:
                    try:
                        count = int(count_input)
                        if count <= 0:
                            await event.respond(
                                "❌ تعداد باید بیشتر از صفر باشد!",
                                buttons=Button.inline("❌ لغو", b"cancel")
                            )
                            return
                        selected_accounts = active_accounts[:min(count, len(active_accounts))]
                    except ValueError:
                        await event.respond(
                            "❌ لطفاً یک عدد معتبر یا /all ارسال کنید.",
                            buttons=Button.inline("❌ لغو", b"cancel")
                        )
                        return
                
                total = len(selected_accounts)
                
                # نمایش پیش‌نمایش پیام
                preview_text = message_text[:100] + "..." if len(message_text) > 100 else message_text
                
                # ارسال پیام شروع
                progress_msg = await event.respond(
                    f"⏳ **شروع عملیات ارسال پیام**\n\n"
                    f"👤 مقصد: {target}\n"
                    f"💬 پیام: {preview_text}\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"⏱ تاخیر بین هر عملیات: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید..."
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال ارسال...**\n\n"
                            f"👤 مقصد: {target}\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}"
                        )
                    except:
                        pass
                
                # ارسال دسته‌جمعی با تایمر
                session_paths = [acc.session_path for acc in selected_accounts]
                results = await self.message_sender.bulk_send_message(
                    session_paths,
                    target,
                    message_text,
                    progress_callback=update_progress
                )
                
                # نمایش نتایج
                results_text = "📊 **نتایج ارسال پیام:**\n\n"
                results_text += f"👤 مقصد: {target}\n"
                results_text += f"💬 پیام: {preview_text}\n\n"
                
                for i, detail in enumerate(results['details'][:10], 1):  # نمایش 10 مورد اول
                    phone_short = selected_accounts[i-1].phone[-4:] if selected_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        results_text += f"✅ {phone_short}: موفق\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                
                if len(results['details']) > 10:
                    results_text += f"\n... و {len(results['details']) - 10} مورد دیگر\n"
                
                results_text += f"\n✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("💬 ارسال مجدد", b"send_message")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_message', user_id, f"{target} - {results['success']}/{total}")
                del self.user_states[user_id]
            
            elif step == 'react_link':
                # دریافت لینک پست
                post_link = event.message.text.strip()
                
                # تجزیه لینک پست
                try:
                    # فرمت: https://t.me/channel/123 یا https://t.me/c/1234567890/123
                    if '/c/' in post_link:
                        # لینک خصوصی
                        parts = post_link.split('/')
                        channel_id = int('-100' + parts[-2])
                        message_id = int(parts[-1])
                        channel_link = str(channel_id)
                    else:
                        # لینک عمومی
                        parts = post_link.split('/')
                        channel_link = parts[-2]
                        message_id = int(parts[-1])
                    
                    # دریافت اکانت‌های کاربر
                    accounts = await self.db.get_accounts(user_id)
                    active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                    
                    if not active_accounts:
                        await event.respond(
                            "❌ شما اکانت فعالی ندارید.",
                            buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                        )
                        del self.user_states[user_id]
                        return
                    
                    # ذخیره اطلاعات و پرسیدن تعداد اکانت
                    state['channel_link'] = channel_link
                    state['message_id'] = message_id
                    state['active_accounts'] = active_accounts
                    state['step'] = 'react_count'
                    
                    await event.respond(
                        f"📊 **انتخاب تعداد اکانت**\n\n"
                        f"شما {len(active_accounts)} اکانت فعال دارید.\n\n"
                        f"چند تا اکانت برای ری‌اکشن استفاده شود؟\n\n"
                        f"💡 عدد ارسال کنید (مثلاً 5) یا:\n"
                        f"• /all برای همه اکانت‌ها",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
                    
                except (ValueError, IndexError) as e:
                    await event.respond(
                        "❌ لینک نامعتبر است!\n\n"
                        "لطفاً لینک را به فرمت صحیح ارسال کنید:\n"
                        "https://t.me/channel/123",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
            
            elif step == 'react_count':
                # دریافت تعداد اکانت
                count_input = event.message.text.strip()
                
                active_accounts = state['active_accounts']
                channel_link = state['channel_link']
                message_id = state['message_id']
                
                # تعیین تعداد اکانت
                if count_input.lower() == '/all':
                    selected_accounts = active_accounts
                else:
                    try:
                        count = int(count_input)
                        if count <= 0:
                            await event.respond(
                                "❌ تعداد باید بیشتر از صفر باشد!",
                                buttons=Button.inline("❌ لغو", b"cancel")
                            )
                            return
                        selected_accounts = active_accounts[:min(count, len(active_accounts))]
                    except ValueError:
                        await event.respond(
                            "❌ لطفاً یک عدد معتبر یا /all ارسال کنید.",
                            buttons=Button.inline("❌ لغو", b"cancel")
                        )
                        return
                
                total = len(selected_accounts)
                
                # ارسال پیام شروع
                progress_msg = await event.respond(
                    f"⏳ **شروع عملیات ری‌اکشن و سین**\n\n"
                    f"📢 کانال: {channel_link}\n"
                    f"📨 پست: {message_id}\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"❤️ هر اکانت: 1 ری‌اکشن تصادفی\n"
                    f"⏱ تاخیر بین هر عملیات: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید..."
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال ری‌اکشن...**\n\n"
                            f"📢 کانال: {channel_link}\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}"
                        )
                    except:
                        pass
                
                # ری‌اکشن دسته‌جمعی
                session_paths = [acc.session_path for acc in selected_accounts]
                results = await self.reaction_manager.bulk_react_and_view(
                    session_paths,
                    channel_link,
                    message_id,
                    reaction_count=3,
                    progress_callback=update_progress
                )
                
                # نمایش نتایج
                results_text = "📊 **نتایج ری‌اکشن و سین:**\n\n"
                results_text += f"📢 کانال: {channel_link}\n"
                results_text += f"📨 پست: {message_id}\n\n"
                
                for i, detail in enumerate(results['details'][:10], 1):
                    phone_short = selected_accounts[i-1].phone[-4:] if selected_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        reaction = result.get('reactions_sent', [''])[0] if result.get('reactions_sent') else '❓'
                        results_text += f"✅ {phone_short}: {reaction}\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                
                if len(results['details']) > 10:
                    results_text += f"\n... و {len(results['details']) - 10} مورد دیگر\n"
                
                results_text += f"\n✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("❤️ ری‌اکشن مجدد", b"react_post")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_reaction', user_id, f"{channel_link}/{message_id} - {results['success']}/{total}")
                del self.user_states[user_id]
            
            elif step == 'block_target':
                # دریافت یوزرنیم یا آیدی کاربر برای بلاک
                target = event.message.text.strip()
                
                # دریافت اکانت‌های کاربر
                accounts = await self.db.get_accounts(user_id)
                active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                
                if not active_accounts:
                    await event.respond(
                        "❌ شما اکانت فعالی ندارید.",
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                    del self.user_states[user_id]
                    return
                
                total = len(active_accounts)
                
                # ارسال پیام شروع
                progress_msg = await event.respond(
                    f"⏳ **شروع عملیات بلاک**\n\n"
                    f"👤 کاربر: {target}\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"⏱ تاخیر بین هر عملیات: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید..."
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال بلاک...**\n\n"
                            f"👤 کاربر: {target}\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}"
                        )
                    except:
                        pass
                
                # بلاک دسته‌جمعی با تایمر
                session_paths = [acc.session_path for acc in active_accounts]
                results = await self.block_manager.bulk_block(
                    session_paths,
                    target,
                    progress_callback=update_progress
                )
                
                # نمایش نتایج
                results_text = "📊 **نتایج بلاک:**\n\n"
                results_text += f"👤 کاربر: {target}\n\n"
                
                for i, detail in enumerate(results['details'][:10], 1):  # نمایش 10 مورد اول
                    phone_short = active_accounts[i-1].phone[-4:] if active_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        results_text += f"✅ {phone_short}: موفق\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                
                if len(results['details']) > 10:
                    results_text += f"\n... و {len(results['details']) - 10} مورد دیگر\n"
                
                results_text += f"\n✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("🚫 بلاک/انبلاک", b"block_user")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_block', user_id, f"{target} - {results['success']}/{total}")
                del self.user_states[user_id]
            
            elif step == 'unblock_target':
                # دریافت یوزرنیم یا آیدی کاربر برای انبلاک
                target = event.message.text.strip()
                
                # دریافت اکانت‌های کاربر
                accounts = await self.db.get_accounts(user_id)
                active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                
                if not active_accounts:
                    await event.respond(
                        "❌ شما اکانت فعالی ندارید.",
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                    del self.user_states[user_id]
                    return
                
                total = len(active_accounts)
                
                # ارسال پیام شروع
                progress_msg = await event.respond(
                    f"⏳ **شروع عملیات انبلاک**\n\n"
                    f"👤 کاربر: {target}\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"⏱ تاخیر بین هر عملیات: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید..."
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال انبلاک...**\n\n"
                            f"👤 کاربر: {target}\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}"
                        )
                    except:
                        pass
                
                # انبلاک دسته‌جمعی با تایمر
                session_paths = [acc.session_path for acc in active_accounts]
                results = await self.block_manager.bulk_unblock(
                    session_paths,
                    target,
                    progress_callback=update_progress
                )
                
                # نمایش نتایج
                results_text = "📊 **نتایج انبلاک:**\n\n"
                results_text += f"👤 کاربر: {target}\n\n"
                
                for i, detail in enumerate(results['details'][:10], 1):  # نمایش 10 مورد اول
                    phone_short = active_accounts[i-1].phone[-4:] if active_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        results_text += f"✅ {phone_short}: موفق\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                
                if len(results['details']) > 10:
                    results_text += f"\n... و {len(results['details']) - 10} مورد دیگر\n"
                
                results_text += f"\n✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("🚫 بلاک/انبلاک", b"block_user")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_unblock', user_id, f"{target} - {results['success']}/{total}")
                del self.user_states[user_id]
            
            elif step == 'set_backup_channel':
                # دریافت آیدی کانال بکاپ
                try:
                    channel_id = int(event.message.text.strip())
                    self.backup_manager.set_backup_channel(channel_id)
                    
                    # ذخیره در دیتابیس
                    await self.db.set_setting('backup_channel_id', str(channel_id))
                    
                    await event.respond(
                        f"✅ **کانال بکاپ تنظیم شد!**\n\n"
                        f"🆔 آیدی کانال: `{channel_id}`\n\n"
                        f"این تنظیمات در دیتابیس ذخیره شد و در اجراهای بعدی ربات، دیگر نیازی به تنظیم مجدد نیست.\n\n"
                        f"حالا می‌توانید بکاپ بگیرید.",
                        buttons=Button.inline("🔙 پنل ادمین", b"admin_panel")
                    )
                    
                    await self.db.log_action('set_backup_channel', user_id, str(channel_id))
                    del self.user_states[user_id]
                    
                except ValueError:
                    await event.respond(
                        "❌ آیدی نامعتبر است! لطفاً یک عدد صحیح ارسال کنید.\n"
                        "مثال: -1001234567890",
                        buttons=Button.inline("❌ لغو", b"admin_panel")
                    )
            
            elif step == 'scenario_input':
                # دریافت سناریو
                scenario_text = event.message.text.strip()
                
                # خط اول یوزرنیم ربات است
                lines = scenario_text.split('\n')
                if not lines:
                    await event.respond(
                        "❌ سناریو خالی است!",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
                    return
                
                bot_username = lines[0].strip().lstrip('@')
                scenario_commands = '\n'.join(lines[1:])
                
                # تجزیه سناریو
                scenario = self.bot_automation.parse_scenario(scenario_commands)
                
                if not scenario:
                    await event.respond(
                        "❌ سناریو نامعتبر است! لطفاً فرمت صحیح را رعایت کنید.",
                        buttons=Button.inline("❌ لغو", b"cancel")
                    )
                    return
                
                # دریافت اکانت‌های کاربر
                accounts = await self.db.get_accounts(user_id)
                active_accounts = [acc for acc in accounts if acc.status == 'active' and acc.session_path]
                
                if not active_accounts:
                    await event.respond(
                        "❌ شما اکانت فعالی ندارید.",
                        buttons=Button.inline("🔙 منوی اصلی", b"back_to_menu")
                    )
                    del self.user_states[user_id]
                    return
                
                # نمایش خلاصه سناریو
                scenario_summary = f"🤖 ربات: @{bot_username}\n📋 مراحل:\n"
                for i, step in enumerate(scenario, 1):
                    action = step['action']
                    value = step['value'][:30] if len(step['value']) > 30 else step['value']
                    scenario_summary += f"{i}. {action}: {value}\n"
                
                # ذخیره اطلاعات و پرسیدن تعداد اکانت
                state['bot_username'] = bot_username
                state['scenario'] = scenario
                state['scenario_summary'] = scenario_summary
                state['active_accounts'] = active_accounts
                state['step'] = 'scenario_count'
                
                await event.respond(
                    f"📊 **انتخاب تعداد اکانت**\n\n"
                    f"شما {len(active_accounts)} اکانت فعال دارید.\n\n"
                    f"چند تا اکانت برای اجرای سناریو استفاده شود؟\n\n"
                    f"💡 عدد ارسال کنید (مثلاً 5) یا:\n"
                    f"• /all برای همه اکانت‌ها",
                    buttons=Button.inline("❌ لغو", b"cancel")
                )
            
            elif step == 'scenario_count':
                # دریافت تعداد اکانت
                count_input = event.message.text.strip()
                
                active_accounts = state['active_accounts']
                bot_username = state['bot_username']
                scenario = state['scenario']
                scenario_summary = state['scenario_summary']
                
                # تعیین تعداد اکانت
                if count_input.lower() == '/all':
                    selected_accounts = active_accounts
                else:
                    try:
                        count = int(count_input)
                        if count <= 0:
                            await event.respond(
                                "❌ تعداد باید بیشتر از صفر باشد!",
                                buttons=Button.inline("❌ لغو", b"cancel")
                            )
                            return
                        selected_accounts = active_accounts[:min(count, len(active_accounts))]
                    except ValueError:
                        await event.respond(
                            "❌ لطفاً یک عدد معتبر یا /all ارسال کنید.",
                            buttons=Button.inline("❌ لغو", b"cancel")
                        )
                        return
                
                total = len(selected_accounts)
                
                # ایجاد flag برای لغو عملیات
                cancel_flag = {'cancelled': False}
                self.running_operations[user_id] = cancel_flag
                
                # ارسال پیام شروع با دکمه لغو
                progress_msg = await event.respond(
                    f"⏳ **شروع اجرای سناریو**\n\n"
                    f"{scenario_summary}\n"
                    f"📊 تعداد اکانت‌ها: {total}\n"
                    f"⏱ تاخیر بین هر اکانت: {Config.DELAY_BETWEEN_ACTIONS}-{Config.DELAY_BETWEEN_ACTIONS + Config.DELAY_RANDOM_RANGE} ثانیه\n\n"
                    f"لطفاً صبر کنید...",
                    buttons=Button.inline("🛑 لغو عملیات", b"cancel_scenario")
                )
                
                # تابع callback برای بروزرسانی پیشرفت
                async def update_progress(current, total, message):
                    try:
                        await progress_msg.edit(
                            f"⏳ **در حال اجرا...**\n\n"
                            f"🤖 ربات: @{bot_username}\n"
                            f"📊 پیشرفت: {current}/{total}\n"
                            f"💬 {message}",
                            buttons=Button.inline("🛑 لغو عملیات", b"cancel_scenario")
                        )
                    except:
                        pass
                
                # اجرای دسته‌جمعی سناریو
                session_paths = [acc.session_path for acc in selected_accounts]
                results = await self.bot_automation.bulk_execute_scenario(
                    session_paths,
                    bot_username,
                    scenario,
                    progress_callback=update_progress,
                    cancel_flag=cancel_flag
                )
                
                # حذف flag عملیات
                if user_id in self.running_operations:
                    del self.running_operations[user_id]
                
                # نمایش نتایج
                results_text = "📊 **نتایج اجرای سناریو:**\n\n"
                results_text += f"🤖 ربات: @{bot_username}\n\n"
                
                for i, detail in enumerate(results['details'][:5], 1):  # نمایش 5 مورد اول
                    phone_short = selected_accounts[i-1].phone[-4:] if selected_accounts[i-1].phone else "****"
                    result = detail['result']
                    
                    if result['success']:
                        results_text += f"✅ {phone_short}:\n"
                        for step_result in result.get('executed_steps', [])[:3]:
                            results_text += f"   {step_result}\n"
                    else:
                        results_text += f"❌ {phone_short}: {result['message'][:30]}\n"
                    
                    results_text += "\n"
                
                if len(results['details']) > 5:
                    results_text += f"... و {len(results['details']) - 5} اکانت دیگر\n\n"
                
                results_text += f"✅ موفق: {results['success']}\n"
                results_text += f"❌ ناموفق: {results['failed']}"
                
                if results.get('cancelled', 0) > 0:
                    results_text += f"\n🛑 لغو شده: {results['cancelled']}"
                
                await progress_msg.edit(
                    results_text,
                    buttons=[
                        [Button.inline("🎯 سناریو جدید", b"advanced_scenario")],
                        [Button.inline("🔙 منوی اصلی", b"back_to_menu")]
                    ]
                )
                
                await self.db.log_action('bulk_scenario', user_id, f"@{bot_username} - {results['success']}/{total}")
                del self.user_states[user_id]
        
        @self.bot.on(events.CallbackQuery(pattern=b"cancel_scenario"))
        async def cancel_scenario_callback(event):
            """لغو عملیات سناریو در حال اجرا"""
            user_id = event.sender_id
            
            if user_id in self.running_operations:
                # تنظیم flag لغو
                self.running_operations[user_id]['cancelled'] = True
                await event.answer("🛑 در حال لغو عملیات...", alert=True)
                
                # ویرایش پیام
                try:
                    await event.edit(
                        event.message.text + "\n\n🛑 **درخواست لغو دریافت شد...**",
                        buttons=None
                    )
                except:
                    pass
            else:
                await event.answer("⚠️ عملیاتی در حال اجرا نیست", alert=True)
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_set_backup_channel"))
        async def admin_set_backup_channel_callback(event):
            """تنظیم کانال بکاپ"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            await event.edit(
                "⚙️ **تنظیم کانال بکاپ**\n\n"
                "آیدی عددی کانال بکاپ را ارسال کنید.\n\n"
                "💡 **نکته:** ربات باید ادمین کانال باشد.\n\n"
                "برای دریافت آیدی کانال:\n"
                "1. پیام از کانال فوروارد کنید به @userinfobot\n"
                "2. آیدی عددی را کپی کنید (مثل: -1001234567890)",
                buttons=Button.inline("❌ لغو", b"admin_panel")
            )
            self.user_states[event.sender_id] = {'step': 'set_backup_channel'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_backup"))
        async def admin_backup_callback(event):
            """بکاپ کامل سیستم"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            
            if not self.backup_manager.backup_channel_id:
                await event.edit(
                    "⚠️ **کانال بکاپ تنظیم نشده است!**\n\n"
                    "ابتدا کانال بکاپ را تنظیم کنید.",
                    buttons=[
                        [Button.inline("⚙️ تنظیم کانال", b"admin_set_backup_channel")],
                        [Button.inline("🔙 بازگشت", b"admin_panel")]
                    ]
                )
                return
            
            progress_msg = await event.edit(
                "⏳ **در حال بکاپ گیری...**\n\n"
                "لطفاً صبر کنید..."
            )
            
            try:
                # بکاپ دیتابیس
                await progress_msg.edit(
                    "⏳ **در حال بکاپ دیتابیس...**\n\n"
                    "📊 مرحله 1 از 3"
                )
                
                db_result = await self.backup_manager.backup_database(Config.DATABASE_PATH)
                
                if not db_result['success']:
                    await progress_msg.edit(
                        f"❌ خطا در بکاپ دیتابیس:\n{db_result['message']}",
                        buttons=Button.inline("🔙 بازگشت", b"admin_panel")
                    )
                    return
                
                # آپلود دیتابیس به کانال
                await progress_msg.edit(
                    "⏳ **در حال آپلود دیتابیس...**\n\n"
                    "📊 مرحله 2 از 3"
                )
                
                upload_db_result = await self.backup_manager.upload_database_backup(
                    db_result['backup_path']
                )
                
                # بکاپ سشن‌ها (زیپ شده)
                await progress_msg.edit(
                    "⏳ **در حال بکاپ سشن‌ها...**\n\n"
                    "📊 مرحله 3 از 3"
                )
                
                accounts = await self.db.get_accounts()
                session_paths = [acc.session_path for acc in accounts if acc.session_path and Path(acc.session_path).exists()]
                
                if session_paths:
                    # ساخت فایل زیپ
                    zip_result = await self.backup_manager.create_sessions_zip(session_paths)
                    
                    if zip_result['success']:
                        # آپلود فایل زیپ به کانال
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        caption = (
                            f"📦 **بکاپ سشن‌ها (زیپ شده)**\n\n"
                            f"📅 تاریخ: {timestamp}\n"
                            f"📱 تعداد سشن‌ها: {zip_result['total_sessions']}\n"
                            f"📁 فایل: {zip_result['zip_filename']}"
                        )
                        
                        await self.bot.send_file(
                            self.backup_manager.backup_channel_id,
                            zip_result['zip_path'],
                            caption=caption
                        )
                        
                        # حذف فایل زیپ موقت
                        Path(zip_result['zip_path']).unlink()
                        
                        sessions_status = f"✅ {zip_result['total_sessions']} سشن در فایل زیپ"
                    else:
                        sessions_status = f"❌ خطا در زیپ کردن"
                else:
                    sessions_status = "⚠️ سشنی یافت نشد"
                
                # نمایش نتیجه
                result_text = "✅ **بکاپ کامل انجام شد!**\n\n"
                result_text += f"💾 دیتابیس: {'✅ موفق' if upload_db_result['success'] else '❌ ناموفق'}\n"
                result_text += f"📦 سشن‌ها: {sessions_status}\n"
                result_text += f"📊 کل اکانت‌ها: {len(accounts)}\n\n"
                result_text += f"📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                await progress_msg.edit(
                    result_text,
                    buttons=Button.inline("🔙 بازگشت", b"admin_panel")
                )
                
                await self.db.log_action('full_backup', event.sender_id, f"{len(session_paths)}/{len(accounts)}")
                
            except Exception as e:
                logger.exception(f"خطا در بکاپ: {e}")
                await progress_msg.edit(
                    f"❌ **خطا در بکاپ:**\n{str(e)}",
                    buttons=Button.inline("🔙 بازگشت", b"admin_panel")
                )
        
        @self.bot.on(events.CallbackQuery(pattern=b"admin_restore"))
        async def admin_restore_callback(event):
            """ریستور بکاپ"""
            # فقط سازنده دسترسی داره
            if not await self._check_creator_access(event):
                return
            
            await event.answer()
            await event.edit(
                "📥 **ریستور بکاپ**\n\n"
                "فایل بکاپ دیتابیس (.db) را ارسال کنید.\n\n"
                "⚠️ **هشدار:** دیتابیس فعلی جایگزین خواهد شد!\n"
                "یک بکاپ امنیتی قبل از ریستور ساخته می‌شود.",
                buttons=Button.inline("❌ لغو", b"admin_panel")
            )
            self.user_states[event.sender_id] = {'step': 'restore_backup'}
        
        @self.bot.on(events.CallbackQuery(pattern=b"advanced_scenario"))
        async def advanced_scenario_callback(event):
            """شروع فرآیند سناریو پیشرفته"""
            # بررسی دسترسی ادمین
            if not await self._check_admin_access(event):
                return
            
            await event.answer()
            
            accounts = await self.db.get_accounts(event.sender_id)
            
            if not accounts:
                await event.edit(
                    "❌ شما هنوز اکانتی اضافه نکرده‌اید.\n"
                    "ابتدا یک اکانت اضافه کنید.",
                    buttons=Button.inline("➕ افزودن اکانت", b"add_account")
                )
                return
            
            await event.edit(
                "🎯 **سناریو پیشرفته ربات**\n\n"
                "با این قابلیت می‌توانید یک سناریو کامل برای تعامل با ربات‌ها تعریف کنید.\n\n"
                "📝 **فرمت سناریو:**\n"
                "```\n"
                "@bot_username\n"
                "start: ref_id\n"
                "send: متن پیام\n"
                "click: کلمه کلیدی دکمه\n"
                "join: لینک کانال\n"
                "leave: لینک کانال\n"
                "wait: 3\n"
                "```\n\n"
                "🎬 **مثال واقعی:**\n"
                "```\n"
                "@Startraygannetbot\n"
                "start: AAAAACWiOtQ\n"
                "click: عضویت\n"
                "join: https://t.me/mychannel\n"
                "send: سلام من هستم\n"
                "click: تایید\n"
                "```\n\n"
                "📋 **دستورات موجود:**\n"
                "• `start: ref_id` → استارت با رفرال\n"
                "• `send: متن` → ارسال پیام به ربات\n"
                "• `click: کلمه` → کلیک روی دکمه (جستجوی جزئی)\n"
                "• `join: لینک` → جوین کانال/گروه\n"
                "• `leave: لینک` → لفت کانال/گروه\n"
                "• `wait: ثانیه` → صبر کردن\n"
                "• `#` → کامنت (نادیده گرفته می‌شود)\n\n"
                "💡 **نکات:**\n"
                "• خط اول باید یوزرنیم ربات باشه\n"
                "• برای کلیک دکمه، فقط یک کلمه کلیدی کافیه\n"
                "• می‌تونی چند دکمه پشت سر هم کلیک کنی\n"
                "• برای join/leave از لینک یا یوزرنیم استفاده کن\n"
                "• بین مراحل 2 ثانیه صبر می‌کنه\n\n"
                "حالا سناریو خودت رو بفرست:",
                buttons=Button.inline("❌ لغو", b"cancel")
            )
            self.user_states[event.sender_id] = {'step': 'scenario_input'}

        @self.bot.on(events.NewMessage(func=lambda e: e.message.document and e.sender_id in Config.ADMIN_IDS))
        async def document_handler(event):
            """هندلر دریافت فایل (برای ریستور بکاپ)"""
            user_id = event.sender_id
            
            if user_id not in self.user_states:
                return
            
            state = self.user_states[user_id]
            step = state.get('step')
            
            if step == 'restore_backup':
                # دریافت فایل بکاپ
                document = event.message.document
                
                # بررسی پسوند فایل
                if not document.attributes[0].file_name.endswith('.db'):
                    await event.respond(
                        "❌ فایل نامعتبر است! فقط فایل‌های .db پذیرفته می‌شوند.",
                        buttons=Button.inline("🔙 پنل ادمین", b"admin_panel")
                    )
                    return
                
                progress_msg = await event.respond("⏳ در حال دانلود فایل...")
                
                try:
                    # دانلود فایل
                    temp_backup_path = Path('data') / 'temp_restore.db'
                    await event.message.download_media(file=str(temp_backup_path))
                    
                    await progress_msg.edit("⏳ در حال ریستور دیتابیس...")
                    
                    # ریستور دیتابیس
                    result = await self.backup_manager.restore_database(
                        str(temp_backup_path),
                        Config.DATABASE_PATH
                    )
                    
                    if result['success']:
                        await progress_msg.edit(
                            "✅ **دیتابیس با موفقیت ریستور شد!**\n\n"
                            "⚠️ **توجه:** برای اعمال تغییرات، ربات را ریستارت کنید.\n\n"
                            "یک بکاپ امنیتی از دیتابیس قبلی ساخته شد.",
                            buttons=Button.inline("🔙 پنل ادمین", b"admin_panel")
                        )
                        
                        await self.db.log_action('restore_backup', user_id, 'success')
                    else:
                        await progress_msg.edit(
                            f"❌ **خطا در ریستور:**\n{result['message']}",
                            buttons=Button.inline("🔙 پنل ادمین", b"admin_panel")
                        )
                    
                    # حذف فایل موقت
                    if temp_backup_path.exists():
                        temp_backup_path.unlink()
                    
                    del self.user_states[user_id]
                    
                except Exception as e:
                    logger.exception(f"خطا در ریستور: {e}")
                    await progress_msg.edit(
                        f"❌ **خطا:**\n{str(e)}",
                        buttons=Button.inline("🔙 پنل ادمین", b"admin_panel")
                    )
                    del self.user_states[user_id]
