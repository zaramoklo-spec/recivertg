"""ماژول مدیریت یادداشت‌های رباتها"""
import logging
from typing import Optional, Dict, List
from src.database import Database

logger = logging.getLogger(__name__)

class NoteManager:
    """کلاس مدیریت یادداشت‌های رباتها"""
    
    def __init__(self, db: Database):
        """مقداردهی اولیه"""
        self.db = db
    
    async def add_note(self, user_id: int, bot_username: str, note_text: str,
                      scenario_text: Optional[str] = None) -> bool:
        """
        افزودن یادداشت برای ربات
        
        Args:
            user_id: آیدی کاربر
            bot_username: یوزرنیم ربات
            note_text: متن یادداشت
            scenario_text: متن سناریو (اختیاری)
            
        Returns:
            True اگر موفق باشد
        """
        return await self.db.add_bot_note(user_id, bot_username, note_text, scenario_text)
    
    async def get_user_notes(self, user_id: int) -> List[Dict]:
        """
        دریافت همه یادداشت‌های یک کاربر
        
        Args:
            user_id: آیدی کاربر
            
        Returns:
            لیست یادداشت‌ها
        """
        return await self.db.get_user_notes(user_id)
    
    async def get_bot_notes(self, user_id: int, bot_username: str) -> List[Dict]:
        """
        دریافت یادداشت‌های یک ربات خاص
        
        Args:
            user_id: آیدی کاربر
            bot_username: یوزرنیم ربات
            
        Returns:
            لیست یادداشت‌ها
        """
        return await self.db.get_bot_notes(user_id, bot_username)
    
    async def delete_note(self, note_id: int, user_id: int) -> bool:
        """
        حذف یادداشت
        
        Args:
            note_id: آیدی یادداشت
            user_id: آیدی کاربر
            
        Returns:
            True اگر موفق باشد
        """
        return await self.db.delete_note(note_id, user_id)
    
    async def update_note(self, note_id: int, user_id: int, note_text: str) -> bool:
        """
        ویرایش یادداشت
        
        Args:
            note_id: آیدی یادداشت
            user_id: آیدی کاربر
            note_text: متن جدید
            
        Returns:
            True اگر موفق باشد
        """
        return await self.db.update_note(note_id, user_id, note_text)
