"""ماژول اتوماسیون پیشرفته ربات‌ها"""
import logging
import asyncio
import random
import string
import re
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
    
    @staticmethod
    def _generate_random_string(length: int) -> str:
        """
        تولید رشته تصادفی
        
        Args:
            length: طول رشته
            
        Returns:
            رشته تصادفی
        """
        # استفاده از حروف کوچک و اعداد
        characters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(characters) for _ in range(length))
    
    @staticmethod
    def _replace_variables(text: str) -> str:
        """
        جایگزینی متغیرهای دینامیک در متن
        
        متغیرهای پشتیبانی شده:
        - {random:N} → رشته تصادفی N حرفی (حروف کوچک + اعداد)
        - {random_upper:N} → رشته تصادفی N حرفی (حروف بزرگ + اعداد)
        - {random_num:N} → عدد تصادفی N رقمی
        
        Args:
            text: متن ورودی
            
        Returns:
            متن با متغیرهای جایگزین شده
        """
        # جایگزینی {random:N}
        pattern = r'\{random:(\d+)\}'
        matches = re.findall(pattern, text)
        for match in matches:
            length = int(match)
            random_str = BotAutomation._generate_random_string(length)
            text = text.replace(f'{{random:{match}}}', random_str, 1)
        
        # جایگزینی {random_upper:N}
        pattern = r'\{random_upper:(\d+)\}'
        matches = re.findall(pattern, text)
        for match in matches:
            length = int(match)
            characters = string.ascii_uppercase + string.digits
            random_str = ''.join(random.choice(characters) for _ in range(length))
            text = text.replace(f'{{random_upper:{match}}}', random_str, 1)
        
        # جایگزینی {random_num:N}
        pattern = r'\{random_num:(\d+)\}'
        matches = re.findall(pattern, text)
        for match in matches:
            length = int(match)
            random_num = ''.join(random.choice(string.digits) for _ in range(length))
            text = text.replace(f'{{random_num:{match}}}', random_num, 1)
        
        return text
    
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
                
                # جایگزینی متغیرهای دینامیک
                value = self._replace_variables(value)
                
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
                            
                            # بررسی اینکه آیا value یک شماره است (با # یا بدون #)
                            button_index = None
                            if value.startswith('#'):
                                # فرمت: #0, #1, #2
                                try:
                                    button_index = int(value[1:])
                                except ValueError:
                                    pass
                            elif value.isdigit():
                                # فرمت: 0, 1, 2
                                button_index = int(value)
                            
                            if button_index is not None:
                                # کلیک با شماره دکمه
                                all_buttons = []
                                for row in messages[0].buttons:
                                    for button in row:
                                        all_buttons.append(button)
                                
                                if 0 <= button_index < len(all_buttons):
                                    button = all_buttons[button_index]
                                    button_text = button.text if hasattr(button, 'text') else str(button)
                                    await button.click()
                                    button_found = True
                                    executed_steps.append(f"✅ کلیک دکمه #{button_index}: {button_text}")
                                else:
                                    executed_steps.append(f"⚠️ دکمه شماره {button_index} وجود ندارد (تعداد: {len(all_buttons)})")
                            else:
                                # کلیک با جستجوی متن (روش قبلی)
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
                            
                            if not button_found and button_index is None:
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
                    
                    elif action == 'stop':
                        # توقف موقت سناریو
                        # فرمت: stop: N (N ثانیه توقف)
                        # یا: stop: (توقف پیش‌فرض 5 ثانیه)
                        stop_time = int(value) if value and value.isdigit() else 5
                        await asyncio.sleep(stop_time)
                        executed_steps.append(f"⏸ توقف {stop_time} ثانیه")
                    
                    elif action == 'solve_captcha':
                        # حل خودکار کپچای ریاضی
                        # فرمت: solve_captcha: send (ارسال جواب به صورت متن)
                        # یا: solve_captcha: click (کلیک روی دکمه با جواب)
                        try:
                            mode = value.strip().lower() if value else 'send'
                            
                            # صبر کوتاه برای اطمینان از دریافت پیام کپچا
                            await asyncio.sleep(1)
                            
                            # دریافت آخرین پیام ربات
                            messages = await client.get_messages(bot, limit=1)
                            
                            if not messages or not messages[0].text:
                                executed_steps.append(f"⚠️ پیامی برای حل کپچا پیدا نشد")
                                continue
                            
                            last_message = messages[0].text
                            logger.info(f"پیام کپچا: {last_message}")
                            
                            # الگوهای مختلف معادلات ریاضی
                            patterns = [
                                r'(\d+)\s*\+\s*(\d+)\s*=\s*\?',  # 5 + 3 = ?
                                r'(\d+)\s*-\s*(\d+)\s*=\s*\?',   # 81 - 4 = ?
                                r'(\d+)\s*×\s*(\d+)\s*=\s*\?',   # 5 × 3 = ?
                                r'(\d+)\s*\*\s*(\d+)\s*=\s*\?',  # 5 * 3 = ?
                                r'(\d+)\s*÷\s*(\d+)\s*=\s*\?',   # 10 ÷ 2 = ?
                                r'(\d+)\s*/\s*(\d+)\s*=\s*\?',   # 10 / 2 = ?
                                r'(\d+)\s*\+\s*(\d+)',            # 5 + 3
                                r'(\d+)\s*-\s*(\d+)',             # 81 - 4
                                r'(\d+)\s*×\s*(\d+)',             # 5 × 3
                                r'(\d+)\s*\*\s*(\d+)',            # 5 * 3
                                r'(\d+)\s*÷\s*(\d+)',             # 10 ÷ 2
                                r'(\d+)\s*/\s*(\d+)',             # 10 / 2
                            ]
                            
                            answer = None
                            operation = None
                            
                            # جستجوی معادله در متن
                            for pattern in patterns:
                                match = re.search(pattern, last_message)
                                if match:
                                    num1 = int(match.group(1))
                                    num2 = int(match.group(2))
                                    
                                    # تشخیص نوع عملیات
                                    if '+' in match.group(0):
                                        answer = num1 + num2
                                        operation = f"{num1} + {num2}"
                                    elif '-' in match.group(0):
                                        answer = num1 - num2
                                        operation = f"{num1} - {num2}"
                                    elif '×' in match.group(0) or '*' in match.group(0):
                                        answer = num1 * num2
                                        operation = f"{num1} × {num2}"
                                    elif '÷' in match.group(0) or '/' in match.group(0):
                                        if num2 != 0:
                                            answer = num1 // num2  # تقسیم صحیح
                                            operation = f"{num1} ÷ {num2}"
                                    
                                    break
                            
                            if answer is None:
                                executed_steps.append(f"⚠️ معادله ریاضی در پیام پیدا نشد")
                                logger.warning(f"معادله پیدا نشد در: {last_message}")
                                continue
                            
                            logger.info(f"معادله حل شد: {operation} = {answer}")
                            
                            # ارسال جواب بر اساس mode
                            if mode == 'send':
                                # ارسال جواب به صورت متن
                                await client.send_message(bot, str(answer))
                                executed_steps.append(f"✅ کپچا حل شد: {operation} = {answer} (ارسال شد)")
                            
                            elif mode == 'click':
                                # کلیک روی دکمه با جواب
                                messages = await client.get_messages(bot, limit=1)
                                
                                if messages and messages[0].buttons:
                                    button_found = False
                                    answer_str = str(answer)
                                    
                                    for row in messages[0].buttons:
                                        for button in row:
                                            button_text = button.text if hasattr(button, 'text') else str(button)
                                            
                                            # جستجوی جواب در متن دکمه
                                            if answer_str in button_text or button_text.strip() == answer_str:
                                                await button.click()
                                                button_found = True
                                                executed_steps.append(f"✅ کپچا حل شد: {operation} = {answer} (کلیک شد)")
                                                break
                                        
                                        if button_found:
                                            break
                                    
                                    if not button_found:
                                        executed_steps.append(f"⚠️ دکمه با جواب '{answer}' پیدا نشد")
                                else:
                                    executed_steps.append(f"⚠️ دکمه‌ای برای کلیک وجود ندارد")
                            
                            else:
                                executed_steps.append(f"❌ mode نامعتبر: {mode} (باید send یا click باشد)")
                        
                        except Exception as e:
                            logger.error(f"خطا در حل کپچا: {e}")
                            executed_steps.append(f"❌ خطا در حل کپچا: {str(e)[:30]}")
                    
                    elif action == 'share_phone' or action == 'share_contact':
                        # اشتراک‌گذاری شماره تماس با ربات
                        # فرمت: share_phone: (بدون value - خودکار شماره اکانت رو میفرسته)
                        try:
                            # دریافت اطلاعات کاربر فعلی
                            me = await client.get_me()
                            
                            # ارسال شماره تماس
                            await client.send_message(
                                bot,
                                file=None,
                                message='',
                                contact=me.phone
                            )
                            
                            executed_steps.append(f"✅ شماره تماس به اشتراک گذاشته شد: +{me.phone}")
                            logger.info(f"شماره تماس +{me.phone} با ربات @{bot_username} به اشتراک گذاشته شد")
                            
                        except Exception as e:
                            logger.error(f"خطا در اشتراک‌گذاری شماره: {e}")
                            executed_steps.append(f"❌ خطا در اشتراک‌گذاری شماره: {str(e)[:30]}")
                    
                    elif action == 'forward':
                        # فوروارد پیام‌های اخیر یا پیام خاص
                        # فرمت 1: forward: N, @target (N تا پیام آخر)
                        # فرمت 2: forward: "متن", @target (پیام حاوی متن مشخص)
                        # مثال 1: forward: 5, @mychannel
                        # مثال 2: forward: "لینک شما", @mychannel
                        try:
                            parts = value.split(',', 1)
                            if len(parts) != 2:
                                executed_steps.append(f"❌ فرمت نادرست! استفاده: forward: N, @target یا forward: \"متن\", @target")
                                continue
                            
                            first_part = parts[0].strip()
                            target = parts[1].strip().lstrip('@')
                            
                            # تشخیص نوع: عدد یا متن
                            search_text = None
                            count = None
                            
                            # اگر با " یا ' شروع شده، متن جستجو است
                            if (first_part.startswith('"') and first_part.endswith('"')) or \
                               (first_part.startswith("'") and first_part.endswith("'")):
                                search_text = first_part[1:-1]  # حذف کوتیشن‌ها
                            else:
                                try:
                                    count = int(first_part)
                                except ValueError:
                                    executed_steps.append(f"❌ فرمت نادرست! باید عدد یا \"متن\" باشد")
                                    continue
                            
                            # دریافت entity هدف
                            try:
                                target_entity = await client.get_entity(target)
                            except Exception as e:
                                executed_steps.append(f"❌ هدف '{target}' پیدا نشد: {str(e)[:30]}")
                                continue
                            
                            # دریافت پیام‌ها
                            if search_text:
                                # جستجوی پیام حاوی متن خاص (100 پیام آخر رو چک می‌کنیم)
                                messages = await client.get_messages(bot, limit=100)
                                matching_messages = []
                                
                                for msg in messages:
                                    if msg.text and search_text.lower() in msg.text.lower():
                                        matching_messages.append(msg)
                                
                                if not matching_messages:
                                    executed_steps.append(f"⚠️ پیامی حاوی '{search_text}' پیدا نشد")
                                    continue
                                
                                messages_to_forward = matching_messages
                            else:
                                # دریافت N تا پیام آخر
                                messages = await client.get_messages(bot, limit=count)
                                
                                if not messages:
                                    executed_steps.append(f"⚠️ پیامی برای فوروارد وجود ندارد")
                                    continue
                                
                                messages_to_forward = messages
                            
                            # فوروارد پیام‌ها
                            forwarded_count = 0
                            for msg in reversed(messages_to_forward):  # از قدیمی به جدید
                                try:
                                    await client.forward_messages(target_entity, msg)
                                    forwarded_count += 1
                                    await asyncio.sleep(0.5)  # تاخیر کوچک بین فوروارد
                                except Exception as e:
                                    logger.error(f"خطا در فوروارد پیام: {e}")
                            
                            if search_text:
                                executed_steps.append(f"✅ فوروارد {forwarded_count} پیام حاوی '{search_text}' به @{target}")
                            else:
                                executed_steps.append(f"✅ فوروارد {forwarded_count} پیام به @{target}")
                        
                        except Exception as e:
                            executed_steps.append(f"❌ خطا در فوروارد: {str(e)[:30]}")
                    
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
        اجرای دسته‌جمعی سناریو با قابلیت لغو و مکث
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            bot_username: یوزرنیم ربات
            scenario: لیست مراحل سناریو
            progress_callback: تابع callback برای نمایش پیشرفت
            cancel_flag: دیکشنری برای بررسی لغو/مکث عملیات
            
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
            
            # بررسی مکث - صبر تا resume شود
            while cancel_flag and cancel_flag.get('paused'):
                logger.info(f"عملیات در حالت مکث است، صبر می‌کنیم...")
                await asyncio.sleep(1)  # هر 1 ثانیه چک می‌کنیم
                
                # اگر در حین مکث لغو شد
                if cancel_flag.get('cancelled'):
                    logger.info(f"عملیات در حین مکث لغو شد")
                    results['cancelled'] = total - index + 1
                    return results
            
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
    
    @staticmethod
    def parse_multi_bot_scenario(scenario_text: str) -> List[Dict]:
        """
        تجزیه سناریو چند ربات
        
        فرمت:
        @bot1
        start: ref1
        send: text1
        
        @bot2
        start: ref2
        send: text2
        
        Args:
            scenario_text: متن سناریو
            
        Returns:
            لیست دیکشنری‌ها با bot_username و scenario
        """
        bots = []
        current_bot = None
        current_scenario = []
        
        lines = scenario_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            # خط خالی یا کامنت
            if not line or line.startswith('#'):
                continue
            
            # شروع ربات جدید
            if line.startswith('@'):
                # ذخیره ربات قبلی
                if current_bot and current_scenario:
                    bots.append({
                        'bot_username': current_bot,
                        'scenario': current_scenario
                    })
                
                # شروع ربات جدید
                current_bot = line.lstrip('@')
                current_scenario = []
            
            # دستورات سناریو
            elif ':' in line and current_bot:
                action, value = line.split(':', 1)
                action = action.strip().lower()
                value = value.strip()
                
                current_scenario.append({
                    'action': action,
                    'value': value,
                    'delay': 2
                })
        
        # ذخیره آخرین ربات
        if current_bot and current_scenario:
            bots.append({
                'bot_username': current_bot,
                'scenario': current_scenario
            })
        
        return bots
    
    async def execute_multi_bot_scenario(self, session_path: str, 
                                         bots_scenarios: List[Dict]) -> Dict[str, any]:
        """
        اجرای سناریو چند ربات
        
        Args:
            session_path: مسیر فایل سشن
            bots_scenarios: لیست ربات‌ها و سناریوهایشان
            
        Returns:
            دیکشنری حاوی نتایج
        """
        all_results = []
        
        for bot_data in bots_scenarios:
            bot_username = bot_data['bot_username']
            scenario = bot_data['scenario']
            
            logger.info(f"اجرای سناریو برای ربات @{bot_username}")
            
            result = await self.execute_scenario(session_path, bot_username, scenario)
            all_results.append({
                'bot': bot_username,
                'result': result
            })
            
            # تاخیر بین رباتها
            await asyncio.sleep(2)
        
        return {
            'success': all([r['result']['success'] for r in all_results]),
            'message': f"اجرای {len(all_results)} ربات",
            'results': all_results
        }
    
    async def bulk_execute_multi_bot_scenario(self, session_paths: List[str],
                                              bots_scenarios: List[Dict],
                                              progress_callback=None,
                                              cancel_flag: Optional[Dict] = None) -> Dict[str, any]:
        """
        اجرای دسته‌جمعی سناریو چند ربات با قابلیت لغو و مکث
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            bots_scenarios: لیست ربات‌ها و سناریوهایشان
            progress_callback: تابع callback برای نمایش پیشرفت
            cancel_flag: دیکشنری برای بررسی لغو/مکث عملیات
            
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
            
            # بررسی مکث - صبر تا resume شود
            while cancel_flag and cancel_flag.get('paused'):
                logger.info(f"عملیات در حالت مکث است، صبر می‌کنیم...")
                await asyncio.sleep(1)  # هر 1 ثانیه چک می‌کنیم
                
                # اگر در حین مکث لغو شد
                if cancel_flag.get('cancelled'):
                    logger.info(f"عملیات در حین مکث لغو شد")
                    results['cancelled'] = total - index + 1
                    return results
            
            # محاسبه تاخیر تصادفی
            delay = Config.DELAY_BETWEEN_ACTIONS + random.randint(0, Config.DELAY_RANDOM_RANGE)
            
            # اگر callback داریم، پیشرفت رو نمایش بدیم
            if progress_callback:
                await progress_callback(index, total, f"در حال اجرای سناریو {index}/{total}...")
            
            logger.info(f"اجرای سناریو چند ربات برای اکانت {index}/{total}")
            
            result = await self.execute_multi_bot_scenario(session_path, bots_scenarios)
            
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
