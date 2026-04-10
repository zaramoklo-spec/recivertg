"""ماژول مدیریت رفرال و استارت ربات‌ها"""
import logging
import re
import asyncio
import random
from typing import Optional, Dict, List
from telethon import TelegramClient
from telethon.sessions import StringSession
from pathlib import Path

from src.config import Config

logger = logging.getLogger(__name__)

class ReferralManager:
    """کلاس مدیریت رفرال ربات‌ها"""
    
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        """مقداردهی اولیه"""
        self.api_id = api_id or Config.API_ID
        self.api_hash = api_hash or Config.API_HASH
    
    def parse_referral_link(self, link: str) -> Dict[str, str]:
        """
        تجزیه لینک رفرال
        
        Args:
            link: لینک رفرال ربات
            
        Returns:
            دیکشنری حاوی bot_username و start_param
        """
        link = link.strip()
        
        # فرمت: https://t.me/bot_name?start=ref_id
        pattern1 = r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)\?start=([a-zA-Z0-9_-]+)'
        match = re.match(pattern1, link)
        if match:
            return {
                'bot_username': match.group(1),
                'start_param': match.group(2)
            }
        
        # فرمت: @bot_name ref_id
        pattern2 = r'@?([a-zA-Z0-9_]+)\s+([a-zA-Z0-9_-]+)'
        match = re.match(pattern2, link)
        if match:
            return {
                'bot_username': match.group(1),
                'start_param': match.group(2)
            }
        
        return {'error': 'فرمت لینک نامعتبر است'}
    
    async def start_bot_with_referral(self, session_path: str, bot_username: str, 
                                     start_param: str, click_button: Optional[str] = None) -> Dict[str, any]:
        """
        استارت ربات با لینک رفرال و کلیک دکمه
        
        Args:
            session_path: مسیر فایل سشن
            bot_username: یوزرنیم ربات
            start_param: پارامتر استارت (رفرال)
            click_button: متن دکمه برای کلیک (اختیاری)
            
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
            bot_username = bot_username.lstrip('@')
            
            # دریافت entity ربات
            logger.info(f"استارت ربات @{bot_username} با پارامتر: {start_param}")
            
            try:
                bot = await client.get_entity(bot_username)
            except Exception as e:
                logger.error(f"خطا در پیدا کردن ربات: {e}")
                return {
                    'success': False,
                    'message': f'ربات @{bot_username} پیدا نشد'
                }
            
            # ارسال دستور /start با پارامتر رفرال
            await client.send_message(bot, f'/start {start_param}')
            
            # صبر برای دریافت پاسخ
            await asyncio.sleep(3)
            
            # اگر باید روی دکمه کلیک کنیم
            if click_button:
                logger.info(f"جستجو برای دکمه با کلمه کلیدی: {click_button}")
                
                # دریافت آخرین پیام از ربات
                messages = await client.get_messages(bot, limit=1)
                
                if messages and messages[0].buttons:
                    # جستجو در دکمه‌ها
                    button_found = False
                    all_buttons = []
                    
                    for row in messages[0].buttons:
                        for button in row:
                            button_text = button.text if hasattr(button, 'text') else str(button)
                            all_buttons.append(button_text)
                            
                            # جستجوی جزئی (partial match) - case-insensitive
                            # حذف ایموجی‌ها و فضاهای اضافی برای مقایسه بهتر
                            clean_button = ''.join(c for c in button_text if c.isalnum() or c.isspace()).strip().lower()
                            clean_search = ''.join(c for c in click_button if c.isalnum() or c.isspace()).strip().lower()
                            
                            # اگر کلمه کلیدی در متن دکمه پیدا شد
                            if clean_search in clean_button:
                                logger.info(f"دکمه پیدا شد: '{button_text}' (جستجو: '{click_button}')")
                                
                                # کلیک روی دکمه
                                await button.click()
                                button_found = True
                                
                                # صبر بعد از کلیک
                                await asyncio.sleep(2)
                                
                                return {
                                    'success': True,
                                    'message': f'استارت و کلیک روی "{button_text}" موفق',
                                    'bot_username': bot_username,
                                    'button_clicked': button_text
                                }
                    
                    if not button_found:
                        logger.warning(f"دکمه با کلمه '{click_button}' پیدا نشد. دکمه‌های موجود: {all_buttons}")
                        return {
                            'success': True,
                            'message': f'استارت موفق اما دکمه با کلمه "{click_button}" پیدا نشد',
                            'bot_username': bot_username,
                            'button_clicked': None,
                            'available_buttons': all_buttons[:5]  # نمایش 5 دکمه اول
                        }
                else:
                    return {
                        'success': True,
                        'message': 'استارت موفق اما دکمه‌ای وجود ندارد',
                        'bot_username': bot_username,
                        'button_clicked': None
                    }
            
            logger.info(f"استارت موفق: @{bot_username}")
            
            return {
                'success': True,
                'message': f'با موفقیت به @{bot_username} استارت زده شد',
                'bot_username': bot_username
            }
            
        except Exception as e:
            logger.exception(f"خطا در استارت ربات: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def bulk_start_bot(self, session_paths: List[str], bot_username: str,
                            start_param: str, click_button: Optional[str] = None,
                            progress_callback=None) -> Dict[str, any]:
        """
        استارت دسته‌جمعی ربات با چند اکانت
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            bot_username: یوزرنیم ربات
            start_param: پارامتر استارت (رفرال)
            click_button: متن دکمه برای کلیک (اختیاری)
            progress_callback: تابع callback برای نمایش پیشرفت
            
        Returns:
            دیکشنری حاوی نتایج
        """
        results = {
            'success': 0,
            'failed': 0,
            'button_clicked': 0,
            'details': []
        }
        
        total = len(session_paths)
        
        for index, session_path in enumerate(session_paths, 1):
            # محاسبه تاخیر تصادفی
            delay = Config.DELAY_BETWEEN_ACTIONS + random.randint(0, Config.DELAY_RANDOM_RANGE)
            
            # اگر callback داریم، پیشرفت رو نمایش بدیم
            if progress_callback:
                await progress_callback(index, total, f"در حال استارت اکانت {index}/{total}...")
            
            logger.info(f"استارت اکانت {index}/{total} - تاخیر: {delay}s")
            
            result = await self.start_bot_with_referral(
                session_path, 
                bot_username, 
                start_param,
                click_button
            )
            
            if result['success']:
                results['success'] += 1
                if result.get('button_clicked'):
                    results['button_clicked'] += 1
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
