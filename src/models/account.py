"""مدل‌های داده"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class AccountCredentials:
    """اطلاعات ورود به اکانت"""
    phone: str
    code: str
    password: Optional[str] = None
    
    def __post_init__(self):
        """اعتبارسنجی داده‌ها"""
        self.phone = self.phone.strip()
        self.code = self.code.strip()
        if self.password:
            self.password = self.password.strip()

@dataclass
class LoginResult:
    """نتیجه ورود"""
    success: bool
    message: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    session_path: Optional[str] = None
