"""ماژول مدیریت ری‌اکشن و سین زدن پست‌ها"""
import logging
import asyncio
import random
from typing import Optional, Dict, List
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.tl.types import ReactionEmoji, ReactionCustomEmoji
from pathlib import Path

from src.config import Config

logger = logging.getLogger(__name__)

class ReactionManager:
    """کلاس مدیریت ری‌اکشن و سین زدن"""
    
    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None):
        """مقداردهی اولیه"""
        self.api_id = api_id or Config.API_ID
        self.api_hash = api_hash or Config.API_HASH
    
    async def react_and_view_post(self, session_path: str, channel_link: str, 
                                  message_id: int, reaction_count: int = 5) -> Dict[str, any]:
        """
        ری‌اکشن و سین زدن یک پست
        
        Args:
            session_path: مسیر فایل سشن
            channel_link: لینک یا یوزرنیم کانال
            message_id: آیدی پیام
            reaction_count: تعداد ری‌اکشن‌های تصادفی (پیش‌فرض 5)
            
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
            
            # تجزیه لینک کانال
            username = channel_link.split('/')[-1].lstrip('@')
            
            try:
                # دریافت entity کانال
                channel = await client.get_entity(username)
                
                # سین زدن پست (مشاهده پیام)
                await client(functions.messages.GetMessagesViewsRequest(
                    peer=channel,
                    id=[message_id],
                    increment=True
                ))
                
                logger.info(f"پست {message_id} در {username} سین زده شد")
                
                # دریافت پیام و ری‌اکشن‌های موجود
                message = await client.get_messages(channel, ids=message_id)
                
                if not message:
                    return {
                        'success': False,
                        'message': 'پیام پیدا نشد'
                    }
                
                # دریافت ری‌اکشن‌های موجود که قبلاً روی پست زده شده
                existing_reactions = []
                
                if hasattr(message, 'reactions') and message.reactions:
                    for reaction_count in message.reactions.results:
                        if hasattr(reaction_count.reaction, 'emoticon'):
                            existing_reactions.append(reaction_count.reaction.emoticon)
                
                logger.info(f"ری‌اکشن‌های موجود روی پست: {existing_reactions}")
                
                # اگر ری‌اکشن موجود داریم، از اونها استفاده کن
                if existing_reactions:
                    available_reactions = existing_reactions
                else:
                    # اگر ری‌اکشن موجود نداریم، از لیست پایه استفاده کن
                    available_reactions = [
                        '👍', '👎', '❤', '🔥', '🥰', '👏',
                        '😁', '🤔', '🤯', '😱', '😢', '🎉',
                        '🤩', '🙏', '👌', '🕊', '🤡', '🥱',
                        '😍', '🐳', '🌚', '🌭', '💯', '🤣',
                        '⚡', '🍌', '💔', '🤨', '😐', '🍓',
                        '💋', '😈', '😴', '😭', '🤓', '👻',
                        '👀', '🎃', '🙈', '😇', '😨', '🤝'
                    ]
                
                # انتخاب یک ری‌اکشن تصادفی
                selected_reaction = random.choice(available_reactions)
                
                # ارسال ری‌اکشن
                reactions_sent = []
                
                try:
                    # ارسال یک ری‌اکشن
                    await client(functions.messages.SendReactionRequest(
                        peer=channel,
                        msg_id=message_id,
                        reaction=[ReactionEmoji(emoticon=selected_reaction)]
                    ))
                    reactions_sent = [selected_reaction]
                    logger.info(f"ری‌اکشن {selected_reaction} ارسال شد")
                    
                except Exception as e:
                    logger.warning(f"خطا در ارسال ری‌اکشن {selected_reaction}: {e}")
                
                logger.info(f"{len(reactions_sent)} ری‌اکشن به پست {message_id} در {username} ارسال شد")
                
                return {
                    'success': True,
                    'message': 'ری‌اکشن و سین با موفقیت انجام شد',
                    'reactions_sent': reactions_sent,
                    'view_added': True
                }
                
            except Exception as e:
                logger.error(f"خطا در پردازش کانال: {e}")
                return {
                    'success': False,
                    'message': f'خطا: {str(e)}'
                }
            
        except Exception as e:
            logger.exception(f"خطا در ری‌اکشن و سین: {e}")
            return {
                'success': False,
                'message': f'خطا: {str(e)}'
            }
        
        finally:
            if client:
                await client.disconnect()
    
    async def bulk_react_and_view(self, session_paths: List[str], channel_link: str,
                                  message_id: int, reaction_count: int = 5,
                                  progress_callback=None) -> Dict[str, any]:
        """
        ری‌اکشن و سین دسته‌جمعی
        
        Args:
            session_paths: لیست مسیر فایل‌های سشن
            channel_link: لینک یا یوزرنیم کانال
            message_id: آیدی پیام
            reaction_count: تعداد ری‌اکشن‌های تصادفی
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
                await progress_callback(index, total, f"در حال ری‌اکشن {index}/{total}...")
            
            logger.info(f"ری‌اکشن برای اکانت {index}/{total} - تاخیر: {delay}s")
            
            result = await self.react_and_view_post(
                session_path, 
                channel_link, 
                message_id,
                reaction_count
            )
            
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
