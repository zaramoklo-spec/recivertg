"""مدل‌های دیتابیس"""
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

@dataclass
class User:
    """مدل کاربر"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: Optional[str] = None
    is_admin: bool = False
    is_approved: bool = False  # آیا سازنده بهش دسترسی داده
    referred_by: Optional[int] = None
    referral_count: int = 0

@dataclass
class Account:
    """مدل اکانت"""
    id: Optional[int] = None
    user_id: int = None
    phone: str = None
    telegram_user_id: Optional[int] = None
    telegram_username: Optional[str] = None
    session_path: Optional[str] = None
    created_at: Optional[str] = None
    status: str = "active"  # active, inactive, banned
    added_by: Optional[int] = None  # کسی که این اکانت رو اضافه کرده

class Database:
    """کلاس مدیریت دیتابیس"""
    
    def __init__(self, db_path: str = "data/accounts.db"):
        """مقداردهی اولیه"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def init_db(self):
        """ایجاد جداول دیتابیس"""
        async with aiosqlite.connect(self.db_path) as db:
            # جدول کاربران
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_admin BOOLEAN DEFAULT 0,
                    is_approved BOOLEAN DEFAULT 0,
                    referred_by INTEGER,
                    referral_count INTEGER DEFAULT 0,
                    FOREIGN KEY (referred_by) REFERENCES users (user_id)
                )
            """)
            
            # جدول اکانت‌ها
            await db.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone TEXT NOT NULL,
                    telegram_user_id INTEGER,
                    telegram_username TEXT,
                    session_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    added_by INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (added_by) REFERENCES users (user_id)
                )
            """)
            
            # جدول آمار
            await db.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    user_id INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول تنظیمات
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # جدول پیشرفت سناریوها
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scenario_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    scenario_hash TEXT NOT NULL,
                    scenario_text TEXT NOT NULL,
                    last_account_index INTEGER DEFAULT 0,
                    total_accounts INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'paused',
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    UNIQUE(user_id, scenario_hash)
                )
            """)
            
            await db.commit()
            
            # Migration: اضافه کردن ستون added_by اگر وجود نداره
            try:
                await db.execute("ALTER TABLE accounts ADD COLUMN added_by INTEGER")
                await db.commit()
            except:
                pass  # ستون از قبل وجود داره
            
            # Migration: اضافه کردن ستون is_approved اگر وجود نداره
            try:
                await db.execute("ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT 0")
                await db.commit()
            except:
                pass  # ستون از قبل وجود داره
    
    async def add_user(self, user: User) -> bool:
        """افزودن یا بروزرسانی کاربر"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, last_name, is_admin, is_approved)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user.user_id, user.username, user.first_name, 
                      user.last_name, user.is_admin, user.is_approved))
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در افزودن کاربر: {e}")
            return False
    
    async def get_user(self, user_id: int) -> Optional[User]:
        """دریافت اطلاعات کاربر"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return User(**dict(row))
                return None
    
    async def is_admin(self, user_id: int) -> bool:
        """بررسی ادمین بودن کاربر"""
        user = await self.get_user(user_id)
        return user.is_admin if user else False
    
    async def add_account(self, account: Account) -> Optional[int]:
        """افزودن اکانت جدید"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO accounts 
                    (user_id, phone, telegram_user_id, telegram_username, session_path, status, added_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (account.user_id, account.phone, account.telegram_user_id,
                      account.telegram_username, account.session_path, account.status, account.added_by))
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"خطا در افزودن اکانت: {e}")
            return None
    
    async def get_accounts(self, user_id: Optional[int] = None) -> List[Account]:
        """دریافت لیست اکانت‌ها"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if user_id:
                query = "SELECT * FROM accounts WHERE user_id = ? ORDER BY created_at DESC"
                params = (user_id,)
            else:
                query = "SELECT * FROM accounts ORDER BY created_at DESC"
                params = ()
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [Account(**dict(row)) for row in rows]
    
    async def get_account_by_phone(self, phone: str) -> Optional[Account]:
        """دریافت اکانت با شماره تلفن"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM accounts WHERE phone = ?", (phone,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Account(**dict(row))
                return None
    
    async def update_account_status(self, account_id: int, status: str) -> bool:
        """بروزرسانی وضعیت اکانت"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE accounts SET status = ? WHERE id = ?",
                    (status, account_id)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در بروزرسانی وضعیت: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کلی"""
        async with aiosqlite.connect(self.db_path) as db:
            # تعداد کل کاربران
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]
            
            # تعداد کل اکانت‌ها
            async with db.execute("SELECT COUNT(*) FROM accounts") as cursor:
                total_accounts = (await cursor.fetchone())[0]
            
            # تعداد اکانت‌های فعال
            async with db.execute(
                "SELECT COUNT(*) FROM accounts WHERE status = 'active'"
            ) as cursor:
                active_accounts = (await cursor.fetchone())[0]
            
            # آخرین اکانت‌ها
            async with db.execute(
                "SELECT phone, created_at FROM accounts ORDER BY created_at DESC LIMIT 5"
            ) as cursor:
                recent_accounts = await cursor.fetchall()
            
            return {
                'total_users': total_users,
                'total_accounts': total_accounts,
                'active_accounts': active_accounts,
                'recent_accounts': recent_accounts
            }
    
    async def log_action(self, action: str, user_id: Optional[int] = None, 
                        details: Optional[str] = None):
        """ثبت لاگ عملیات"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO stats (action, user_id, details) VALUES (?, ?, ?)",
                    (action, user_id, details)
                )
                await db.commit()
        except Exception as e:
            print(f"خطا در ثبت لاگ: {e}")
    
    async def add_admin(self, user_id: int) -> bool:
        """اضافه کردن ادمین"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET is_admin = 1 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در اضافه کردن ادمین: {e}")
            return False
    
    async def remove_admin(self, user_id: int) -> bool:
        """حذف ادمین"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET is_admin = 0 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در حذف ادمین: {e}")
            return False
    
    async def approve_user(self, user_id: int) -> bool:
        """تایید دسترسی کاربر"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET is_approved = 1 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در تایید کاربر: {e}")
            return False
    
    async def unapprove_user(self, user_id: int) -> bool:
        """لغو دسترسی کاربر"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET is_approved = 0 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در لغو دسترسی کاربر: {e}")
            return False
    
    async def get_pending_users(self) -> List[User]:
        """دریافت کاربران در انتظار تایید"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE is_approved = 0 AND is_admin = 0 ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [User(**dict(row)) for row in rows]
    
    async def get_all_admins(self) -> List[User]:
        """دریافت لیست همه ادمین‌ها"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE is_admin = 1 ORDER BY user_id"
            ) as cursor:
                rows = await cursor.fetchall()
                return [User(**dict(row)) for row in rows]
    
    async def get_setting(self, key: str) -> Optional[str]:
        """دریافت تنظیمات"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT value FROM settings WHERE key = ?", (key,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else None
        except Exception as e:
            print(f"خطا در دریافت تنظیمات: {e}")
            return None
    
    async def set_setting(self, key: str, value: str) -> bool:
        """ذخیره تنظیمات"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (key, value))
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در ذخیره تنظیمات: {e}")
            return False

    async def save_scenario_progress(self, user_id: int, scenario_text: str, 
                                     last_index: int, total: int) -> bool:
        """ذخیره پیشرفت سناریو"""
        try:
            import hashlib
            scenario_hash = hashlib.md5(scenario_text.encode()).hexdigest()
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO scenario_progress 
                    (user_id, scenario_hash, scenario_text, last_account_index, 
                     total_accounts, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'paused')
                """, (user_id, scenario_hash, scenario_text, last_index, total))
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در ذخیره پیشرفت سناریو: {e}")
            return False
    
    async def get_scenario_progress(self, user_id: int, scenario_text: str) -> Optional[Dict[str, Any]]:
        """دریافت پیشرفت سناریو"""
        try:
            import hashlib
            scenario_hash = hashlib.md5(scenario_text.encode()).hexdigest()
            
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM scenario_progress 
                    WHERE user_id = ? AND scenario_hash = ?
                """, (user_id, scenario_hash)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
                    return None
        except Exception as e:
            print(f"خطا در دریافت پیشرفت سناریو: {e}")
            return None
    
    async def delete_scenario_progress(self, user_id: int, scenario_text: str) -> bool:
        """حذف پیشرفت سناریو"""
        try:
            import hashlib
            scenario_hash = hashlib.md5(scenario_text.encode()).hexdigest()
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    DELETE FROM scenario_progress 
                    WHERE user_id = ? AND scenario_hash = ?
                """, (user_id, scenario_hash))
                await db.commit()
                return True
        except Exception as e:
            print(f"خطا در حذف پیشرفت سناریو: {e}")
            return False
    
    async def get_user_scenario_progresses(self, user_id: int) -> List[Dict[str, Any]]:
        """دریافت همه پیشرفت‌های سناریوی یک کاربر"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM scenario_progress 
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                """, (user_id,)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            print(f"خطا در دریافت پیشرفت‌های سناریو: {e}")
            return []
