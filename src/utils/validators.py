"""توابع اعتبارسنجی"""
import re
from typing import Optional

def validate_phone_number(phone: str) -> bool:
    """
    اعتبارسنجی شماره تلفن
    
    Args:
        phone: شماره تلفن
        
    Returns:
        True اگر معتبر باشد
    """
    # الگوی شماره تلفن بین‌المللی
    pattern = r'^\+?[1-9]\d{1,14}$'
    return bool(re.match(pattern, phone.replace(' ', '').replace('-', '')))

def validate_code(code: str) -> bool:
    """
    اعتبارسنجی کد تایید
    
    Args:
        code: کد تایید
        
    Returns:
        True اگر معتبر باشد
    """
    return code.isdigit() and len(code) == 5

def extract_telegram_code(text: str) -> Optional[str]:
    """
    استخراج کد تایید تلگرام از متن پیام
    
    Args:
        text: متن پیام حاوی کد تایید
        
    Returns:
        کد 5 رقمی یا None
        
    Examples:
        >>> extract_telegram_code("Login code: 96170. Do not give...")
        '96170'
        >>> extract_telegram_code("Your code is 12345")
        '12345'
        >>> extract_telegram_code("96170")
        '96170'
    """
    if not text:
        return None
    
    # الگوهای مختلف برای پیدا کردن کد
    patterns = [
        r'Login code:\s*(\d{5})',  # Login code: 96170
        r'code:\s*(\d{5})',         # code: 96170
        r'code\s+is\s+(\d{5})',     # code is 96170
        r'\b(\d{5})\b',             # هر عدد 5 رقمی مستقل
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            code = match.group(1)
            if validate_code(code):
                return code
    
    return None
