"""ماژول اصلی دریافت اکانت تلگرام"""
import logging
from pathlib import Path
from typing import Optional, Dict
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from src.config import Config
from src.models import AccountCredentials, LoginResult
from src.core.exceptions import InvalidCredentialsError, LoginFailedError, SessionSaveError

logger = logging.getLogger(__name__)

class AccountReceiver:
    """کلاس دریافت و ذخیره اکانت تلگرام"""
    
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        """
        مقداردهی اولیه
        
        Args:
            api_id: شناسه API (اختیاری، از Config استفاده می‌شود)
            api_hash: هش API (اختیاری، از Config استفاده می‌شود)
        """
        self.api_id = api_id or Config.API_ID
        self.api_hash = api_hash or Config.API_HASH
        
        if not self.api_id or not self.api_hash:
            raise ValueError("API_ID و API_HASH الزامی است")
        
        # ذخیره کلاینت‌های فعال
        self.active_clients: Dict[int, TelegramClient] = {}
    
    async def send_code_request(self, phone: str, user_id: int) -> Dict[str, any]:
        """
        ارسال درخواست کد تایید
        
        Args:
            phone: شماره تلفن
            user_id: شناسه کاربر ربات
            
        Returns:
            دیکشنری حاوی وضعیت و پیام
        """
        try:
            # دریافت تنظیمات پروکسی
            proxy = Config.get_proxy_config()
            
            # ایجاد کلاینت جدید
            client = TelegramClient(
                StringSession(),
                self.api_id,
                self.api_hash,
                proxy=proxy
            )
            
            await client.connect()
            
            # ارسال درخواست کد
            logger.info(f"ارسال درخواست کد برای: {phone}")
            sent_code = await client.send_code_request(phone)
            
            # ذخیره کلاینت برای استفاده بعدی
            self.active_clients[user_id] = client
            
            return {
                'success': True,
                'message': 'کد تایید ارسال شد',
                'phone_code_hash': sent_code.phone_code_hash
            }
            
        except errors.PhoneNumberInvalidError:
            logger.error(f"شماره تلفن نامعتبر: {phone}")
            return {
                'success': False,
                'message': 'شماره تلفن نامعتبر است'
            }
        
        except errors.PhoneNumberBannedError:
            logger.error(f"شماره تلفن مسدود شده: {phone}")
            return {
                'success': False,
                'message': 'این شماره تلفن مسدود شده است'
            }
        
        except errors.FloodWaitError as e:
            logger.error(f"محدودیت زمانی: {e.seconds} ثانیه")
            return {
                'success': False,
                'message': f'لطفاً {e.seconds} ثانیه صبر کنید'
            }
        
        except Exception as e:
            logger.exception(f"خطا در ارسال کد: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
    
    async def sign_in_with_code(self, user_id: int, phone: str, code: str) -> Dict[str, any]:
        """
        ورود با کد تایید
        
        Args:
            user_id: شناسه کاربر ربات
            phone: شماره تلفن
            code: کد تایید
            
        Returns:
            دیکشنری حاوی وضعیت و پیام
        """
        client = self.active_clients.get(user_id)
        
        if not client:
            return {
                'success': False,
                'message': 'جلسه منقضی شده. لطفاً دوباره شماره را ارسال کنید',
                'need_restart': True
            }
        
        try:
            logger.info(f"تلاش برای ورود با کد: {phone}")
            
            # ورود با کد
            await client.sign_in(phone=phone, code=code)
            
            # دریافت اطلاعات کاربر
            me = await client.get_me()
            
            # ذخیره سشن
            session_string = client.session.save()
            session_path = await self._save_session(
                phone=phone,
                user_id=me.id,
                session_string=session_string
            )
            
            # پاک کردن کلاینت از حافظه
            await client.disconnect()
            del self.active_clients[user_id]
            
            logger.info(f"ورود موفق: {me.first_name} (@{me.username})")
            
            return {
                'success': True,
                'message': 'ورود با موفقیت انجام شد',
                'user_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'session_path': str(session_path),
                'completed': True
            }
            
        except errors.PhoneCodeInvalidError:
            logger.error("کد تایید نامعتبر است")
            return {
                'success': False,
                'message': 'کد تایید نامعتبر است'
            }
        
        except errors.PhoneCodeExpiredError:
            logger.error("کد تایید منقضی شده است")
            # پاک کردن کلاینت
            await client.disconnect()
            del self.active_clients[user_id]
            return {
                'success': False,
                'message': 'کد تایید منقضی شده است. لطفاً دوباره تلاش کنید',
                'need_restart': True
            }
        
        except errors.SessionPasswordNeededError:
            logger.info("رمز دو مرحله‌ای مورد نیاز است")
            return {
                'success': True,
                'message': 'رمز دو مرحله‌ای مورد نیاز است',
                'need_password': True
            }
        
        except Exception as e:
            logger.exception(f"خطا در ورود: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
    
    async def sign_in_with_password(self, user_id: int, password: str) -> Dict[str, any]:
        """
        ورود با رمز دو مرحله‌ای
        
        Args:
            user_id: شناسه کاربر ربات
            password: رمز دو مرحله‌ای
            
        Returns:
            دیکشنری حاوی وضعیت و پیام
        """
        client = self.active_clients.get(user_id)
        
        if not client:
            return {
                'success': False,
                'message': 'جلسه منقضی شده. لطفاً دوباره شماره را ارسال کنید',
                'need_restart': True
            }
        
        try:
            logger.info("تلاش برای ورود با رمز دو مرحله‌ای")
            
            # ورود با رمز
            await client.sign_in(password=password)
            
            # دریافت اطلاعات کاربر
            me = await client.get_me()
            
            # ذخیره سشن
            session_string = client.session.save()
            phone = me.phone if me.phone else "unknown"
            session_path = await self._save_session(
                phone=phone,
                user_id=me.id,
                session_string=session_string
            )
            
            # پاک کردن کلاینت از حافظه
            await client.disconnect()
            del self.active_clients[user_id]
            
            logger.info(f"ورود موفق: {me.first_name} (@{me.username})")
            
            return {
                'success': True,
                'message': 'ورود با موفقیت انجام شد',
                'user_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'session_path': str(session_path),
                'completed': True
            }
            
        except errors.PasswordHashInvalidError:
            logger.error("رمز دو مرحله‌ای نامعتبر است")
            return {
                'success': False,
                'message': 'رمز دو مرحله‌ای نامعتبر است'
            }
        
        except Exception as e:
            logger.exception(f"خطا در ورود با رمز: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
    
    async def cancel_login(self, user_id: int):
        """لغو فرآیند ورود و بستن کلاینت"""
        if user_id in self.active_clients:
            try:
                await self.active_clients[user_id].disconnect()
            except:
                pass
            del self.active_clients[user_id]
            logger.info(f"فرآیند ورود کاربر {user_id} لغو شد")
    
    async def _save_session(
        self,
        phone: str,
        user_id: int,
        session_string: str
    ) -> Path:
        """
        ذخیره سشن در فایل
        
        Args:
            phone: شماره تلفن
            user_id: شناسه کاربر
            session_string: رشته سشن
            
        Returns:
            مسیر فایل ذخیره شده
        """
        try:
            # نام فایل: phone_userid.session
            filename = f"{phone.replace('+', '')}_{user_id}.session"
            session_path = Config.SESSIONS_DIR / filename
            
            # ذخیره سشن
            session_path.write_text(session_string, encoding='utf-8')
            
            logger.info(f"سشن ذخیره شد: {session_path}")
            return session_path
            
        except Exception as e:
            logger.exception(f"خطا در ذخیره سشن: {e}")
            raise SessionSaveError(f"خطا در ذخیره سشن: {e}")
    
    async def load_session(self, session_path: str) -> TelegramClient:
        """
        بارگذاری سشن از فایل
        
        Args:
            session_path: مسیر فایل سشن
            
        Returns:
            کلاینت تلگرام متصل
        """
        try:
            session_string = Path(session_path).read_text(encoding='utf-8')
            
            client = TelegramClient(
                StringSession(session_string),
                self.api_id,
                self.api_hash
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                raise LoginFailedError("سشن نامعتبر است")
            
            logger.info(f"سشن بارگذاری شد: {session_path}")
            return client
            
        except Exception as e:
            logger.exception(f"خطا در بارگذاری سشن: {e}")
            raise
