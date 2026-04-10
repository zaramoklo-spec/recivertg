"""ماژول مدیریت بلاک و انبلاک کاربران"""
import logging
import asyncio
import random
from typing import Optional, Dict, List
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from pathlib import Path

from src.config import Config

logger = logging.getLogger(__name__)

class BlockManager:
    """کلاس مدیریت بلاک و انبلاک"""
    
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        """مقداردهی اولیه"""
        self.api_id = api_id or Config.API_ID
        self.api_hash = api_hash or Config.API_HASH
    
    async def block_user(self, session_path: str, target: str) -> Dict[str, any]:
        """
        بلاک کردن کاربر
        
        Args:
            session_path: مسیر فایل سشن
            target: یوزرنیم یا آیدی کاربر
            
        Returns:
            دیکشنری حاوی وضعیت
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
            
            try:
                # دریافت entity کاربر
                user = await client.get_entity(target)
                
                # بلاک کردن
                await client(functions.contacts.BlockRequest(id=user))
                
                logger.info(f"کاربر {target} بلاک شد")
                
                return {
                    'success': True,
                    'message': 'کاربر با موفقیت بلاک شد',
                    'target': target,
                    'user_id': user.id
                }
                
            except Exception as e:
                logger.error(f"خطا در بلاک کردن: {e}")
                return {
                    'success': False,
                    'message': f'خطا: {str(e)}'
                }
            
        except Exception as e:
            logger.exception(f"خطا در بلاک: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def unblock_user(self, session_path: str, target: str) -> Dict[str, any]:
        """
        انبلاک کردن کاربر
        
        Args:
            session_path: مسیر فایل سشن
            target: یوزرنیم یا آیدی کاربر
            
        Returns:
            دیکشنری حاوی وضعیت
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
            
            try:
                # دریافت entity کاربر
                user = await client.get_entity(target)
                
                # انبلاک کردن
                await client(functions.contacts.UnblockRequest(id=user))
                
                logger.info(f"کاربر {target} انبلاک شد")
                
                return {
                    'success': True,
                    'message': 'کاربر با موفقیت انبلاک شد',
                    'target': target,
                    'user_id': user.id
                }
                
            except Exception as e:
                logger.error(f"خطا در انبلاک کردن: {e}")
                return {
                    'success': False,
                    'message': f'خطا: {str(e)}'
                }
            
        except Exception as e:
            logger.exception(f"خطا در انبلاک: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def bulk_block(self, session_paths: List[str], target: str,
                        progress_callback=None) -> Dict[str, any]:
        """
        بلاک دسته‌جمعی
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            target: یوزرنیم یا آیدی کاربر
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
                await progress_callback(index, total, f"در حال بلاک {index}/{total}...")
            
            logger.info(f"بلاک برای اکانت {index}/{total} - تاخیر: {delay}s")
            
            result = await self.block_user(session_path, target)
            
            if result['success']:
                results['success'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append({
                'session': Path(session_path).name,
                'result': result
            })
            
            # تاخیر بین عملیات‌ها
            if index < total:
                logger.info(f"صبر {delay} ثانیه قبل از عملیات بعدی...")
                await asyncio.sleep(delay)
        
        return results
    
    async def bulk_unblock(self, session_paths: List[str], target: str,
                          progress_callback=None) -> Dict[str, any]:
        """
        انبلاک دسته‌جمعی
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            target: یوزرنیم یا آیدی کاربر
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
                await progress_callback(index, total, f"در حال انبلاک {index}/{total}...")
            
            logger.info(f"انبلاک برای اکانت {index}/{total} - تاخیر: {delay}s")
            
            result = await self.unblock_user(session_path, target)
            
            if result['success']:
                results['success'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append({
                'session': Path(session_path).name,
                'result': result
            })
            
            # تاخیر بین عملیات‌ها
            if index < total:
                logger.info(f"صبر {delay} ثانیه قبل از عملیات بعدی...")
                await asyncio.sleep(delay)
        
        return results
