"""تنظیمات لاگر"""
import logging
from pathlib import Path

def setup_logger(name: str = __name__, log_file: str = None) -> logging.Logger:
    """
    راه‌اندازی لاگر
    
    Args:
        name: نام لاگر
        log_file: مسیر فایل لاگ (اختیاری)
        
    Returns:
        لاگر تنظیم شده
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # فرمت لاگ
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # هندلر کنسول
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # هندلر فایل (اختیاری)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
