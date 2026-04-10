"""ماژول اتوماسیون پیشرفته ربات‌ها"""
import logging
import asyncio
import random
from typing import Optional, Dict, List
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from pathlib import Path

from src.config import Config

logger = logging.getLogger(__name__)

class BotAutomation:
    """کلاس اتوماسیون پیشرفته ربات‌ها"""
    
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        """مقداردهی اولیه"""
        self.api_id = api_id or Config.API_ID
        self.api_hash = api_hash or Config.API_HASH
    
    async def execute_scenario(self, session_path: str, bot_username: str, 
                               scenario: List[Dict]) -> Dict[str, any]:
        """
        اجرای سناریو کامل
        
        Args:
            session_path: مسیر فایل سشن
            bot_username: یوزرنیم ربات
            scenario: لیست مراحل سناریو
            
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
            
            # حذف @ از یوزرنیم
            bot_username = bot_username.lstrip('@')
            
            # دریافت entity ربات
            try:
                bot = await client.get_entity(bot_username)
            except Exception as e:
                logger.error(f"خطا در پیدا کردن ربات: {e}")
                return {
                    'success': False,
                    'message': f'ربات @{bot_username} پیدا نشد'
                }
            
            logger.info(f"شروع اجرای سناریو برای @{bot_username}")
            
            executed_steps = []
            
            # اجرای هر مرحله
            for step_num, step in enumerate(scenario, 1):
                action = step.get('action')
                value = step.get('value', '')
                delay = step.get('delay', 2)
                
                logger.info(f"مرحله {step_num}: {action} - {value}")
                
                try:
                    if action == 'start':
                        # ارسال /start با پارامتر
                        await client.send_message(bot, f'/start {value}')
                        executed_steps.append(f"✅ استارت با رفرال: {value}")
                    
                    elif action == 'send':
                        # ارسال متن
                        await client.send_message(bot, value)
                        executed_steps.append(f"✅ ارسال پیام: {value[:30]}...")
                    
                    elif action == 'click':
                        # کلیک روی دکمه
                        messages = await client.get_messages(bot, limit=1)
                        
                        if messages and messages[0].buttons:
                            button_found = False
                            
                            for row in messages[0].buttons:
                                for button in row:
                                    button_text = button.text if hasattr(button, 'text') else str(button)
                                    
                                    # جستجوی جزئی
                                    clean_button = ''.join(c for c in button_text if c.isalnum() or c.isspace()).strip().lower()
                                    clean_search = ''.join(c for c in value if c.isalnum() or c.isspace()).strip().lower()
                                    
                                    if clean_search in clean_button:
                                        await button.click()
                                        button_found = True
                                        executed_steps.append(f"✅ کلیک دکمه: {button_text}")
                                        break
                                
                                if button_found:
                                    break
                            
                            if not button_found:
                                executed_steps.append(f"⚠️ دکمه '{value}' پیدا نشد")
                        else:
                            executed_steps.append(f"⚠️ دکمه‌ای وجود ندارد")
                    
                    elif action == 'join':
                        # جوین کانال/گروه
                        channel_link = value.strip()
                        try:
                            # تجزیه لینک
                            if 'joinchat/' in channel_link or '/+' in channel_link:
                                # لینک خصوصی
                                hash_part = channel_link.split('/')[-1].replace('+', '')
                                await client(functions.messages.ImportChatInviteRequest(hash_part))
                            else:
                                # لینک عمومی یا یوزرنیم
                                username = channel_link.split('/')[-1].lstrip('@')
                                await client(functions.channels.JoinChannelRequest(username))
                            
                            executed_steps.append(f"✅ جوین: {channel_link[:30]}")
                        except Exception as e:
                            executed_steps.append(f"❌ جوین ناموفق: {str(e)[:30]}")
                    
                    elif action == 'leave':
                        # لفت کانال/گروه
                        channel_link = value.strip()
                        try:
                            # تجزیه لینک
                            username = channel_link.split('/')[-1].lstrip('@')
                            channel = await client.get_entity(username)
                            await client(functions.channels.LeaveChannelRequest(channel))
                            
                            executed_steps.append(f"✅ لفت: {channel_link[:30]}")
                        except Exception as e:
                            executed_steps.append(f"❌ لفت ناموفق: {str(e)[:30]}")
                    
                    elif action == 'wait':
                        # صبر کردن
                        wait_time = int(value) if value else delay
                        await asyncio.sleep(wait_time)
                        executed_steps.append(f"⏱ صبر {wait_time} ثانیه")
                    
                    # تاخیر بین مراحل
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"خطا در مرحله {step_num}: {e}")
                    executed_steps.append(f"❌ خطا در مرحله {step_num}: {str(e)[:30]}")
            
            return {
                'success': True,
                'message': 'سناریو با موفقیت اجرا شد',
                'bot_username': bot_username,
                'executed_steps': executed_steps
            }
            
        except Exception as e:
            logger.exception(f"خطا در اجرای سناریو: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def bulk_execute_scenario(self, session_paths: List[str], bot_username: str,
                                    scenario: List[Dict], progress_callback=None, 
                                    cancel_flag: Optional[Dict] = None) -> Dict[str, any]:
        """
        اجرای دسته‌جمعی سناریو با قابلیت لغو
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            bot_username: یوزرنیم ربات
            scenario: لیست مراحل سناریو
            progress_callback: تابع callback برای نمایش پیشرفت
            cancel_flag: دیکشنری برای بررسی لغو عملیات
            
        Returns:
            دیکشنری حاوی نتایج
        """
        results = {
            'success': 0,
            'failed': 0,
            'cancelled': 0,
            'details': []
        }
        
        total = len(session_paths)
        
        for index, session_path in enumerate(session_paths, 1):
            # بررسی لغو عملیات
            if cancel_flag and cancel_flag.get('cancelled'):
                logger.info(f"عملیات توسط کاربر لغو شد در مرحله {index}/{total}")
                results['cancelled'] = total - index + 1
                break
            
            # محاسبه تاخیر تصادفی
            delay = Config.DELAY_BETWEEN_ACTIONS + random.randint(0, Config.DELAY_RANDOM_RANGE)
            
            # اگر callback داریم، پیشرفت رو نمایش بدیم
            if progress_callback:
                await progress_callback(index, total, f"در حال اجرای سناریو {index}/{total}...")
            
            logger.info(f"اجرای سناریو برای اکانت {index}/{total} - تاخیر: {delay}s")
            
            result = await self.execute_scenario(session_path, bot_username, scenario)
            
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
    
    @staticmethod
    def parse_scenario(scenario_text: str) -> List[Dict]:
        """
        تجزیه متن سناریو به لیست مراحل
        
        فرمت:
        start: ref_id
        send: متن پیام
        click: کلمه کلیدی دکمه
        wait: 5
        
        Args:
            scenario_text: متن سناریو
            
        Returns:
            لیست مراحل
        """
        scenario = []
        lines = scenario_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if ':' in line:
                action, value = line.split(':', 1)
                action = action.strip().lower()
                value = value.strip()
                
                scenario.append({
                    'action': action,
                    'value': value,
                    'delay': 2
                })
        
        return scenario
