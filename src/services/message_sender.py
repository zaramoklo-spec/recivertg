"""ماژول ارسال پیام"""
import logging
import asyncio
import random
from typing import Optional, Dict, List
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from pathlib import Path

from src.config import Config

logger = logging.getLogger(__name__)

class MessageSender:
    """کلاس ارسال پیام به کاربران"""
    
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        """مقداردهی اولیه"""
        self.api_id = api_id or Config.API_ID
        self.api_hash = api_hash or Config.API_HASH
    
    async def send_message(self, session_path: str, target: str, message: str) -> Dict[str, any]:
        """
        ارسال پیام به کاربر
        
        Args:
            session_path: مسیر فایل سشن
            target: یوزرنیم (@username) یا آیدی عددی کاربر
            message: متن پیام
            
        Returns:
            دیکشنری حاوی وضعیت و پیام
        """
        client = None
        
        try:
            # بارگذاری سشن
            session_string = Path(session_path).read_text(encoding='utf-8')
            
            client = TelegramClient(
                StringSession(session_string),
                self.api_id,
                self.api_hash
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                return {
                    'success': False,
                    'message': 'سشن نامعتبر است'
                }
            
            # حذف @ از یوزرنیم اگر وجود داشته باشد
            if target.startswith('@'):
                target = target[1:]
            
            # تبدیل به int اگر عدد باشد
            if target.isdigit():
                target = int(target)
            
            logger.info(f"ارسال پیام به: {target}")
            
            try:
                # ارسال پیام
                await client.send_message(target, message)
                
                logger.info(f"پیام با موفقیت ارسال شد")
                
                return {
                    'success': True,
                    'message': 'پیام با موفقیت ارسال شد',
                    'target': target
                }
                
            except errors.UserIsBlockedError:
                logger.error("کاربر شما را بلاک کرده است")
                return {
                    'success': False,
                    'message': 'کاربر شما را بلاک کرده است'
                }
            
            except errors.UserIdInvalidError:
                logger.error("آیدی کاربر نامعتبر است")
                return {
                    'success': False,
                    'message': 'آیدی کاربر نامعتبر است'
                }
            
            except errors.PeerIdInvalidError:
                logger.error("کاربر پیدا نشد")
                return {
                    'success': False,
                    'message': 'کاربر پیدا نشد'
                }
            
            except errors.ChatWriteForbiddenError:
                logger.error("شما اجازه ارسال پیام ندارید")
                return {
                    'success': False,
                    'message': 'شما اجازه ارسال پیام ندارید'
                }
            
            except Exception as e:
                logger.error(f"خطا در ارسال پیام: {e}")
                return {
                    'success': False,
                    'message': f'خطا: {str(e)}'
                }
            
        except errors.FloodWaitError as e:
            logger.error(f"محدودیت زمانی: {e.seconds} ثانیه")
            return {
                'success': False,
                'message': f'محدودیت زمانی: {e.seconds} ثانیه صبر کنید'
            }
        
        except Exception as e:
            logger.exception(f"خطا در ارسال پیام: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def bulk_send_message(self, session_paths: List[str], target: str,
                               message: str, progress_callback=None) -> Dict[str, any]:
        """
        ارسال دسته‌جمعی پیام با چند اکانت
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            target: یوزرنیم یا آیدی کاربر مقصد
            message: متن پیام
            progress_callback: تابع callback برای نمایش پیشرفت
            
        Returns:
            دیکشنری حاوی نتایج
        """
        results = {
            'success': 0,
            'failed': 0,
            'details': []
        }
        
        total = len(session_paths)
        
        for index, session_path in enumerate(session_paths, 1):
            # محاسبه تاخیر تصادفی
            delay = Config.DELAY_BETWEEN_ACTIONS + random.randint(0, Config.DELAY_RANDOM_RANGE)
            
            # اگر callback داریم، پیشرفت رو نمایش بدیم
            if progress_callback:
                await progress_callback(index, total, f"در حال ارسال از اکانت {index}/{total}...")
            
            logger.info(f"ارسال پیام از اکانت {index}/{total} - تاخیر: {delay}s")
            
            result = await self.send_message(session_path, target, message)
            
            if result['success']:
                results['success'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append({
                'session': Path(session_path).name,
                'result': result
            })
            
            # تاخیر بین عملیات‌ها (به جز آخرین مورد)
            if index < total:
                logger.info(f"صبر {delay} ثانیه قبل از عملیات بعدی...")
                await asyncio.sleep(delay)
        
        return results
