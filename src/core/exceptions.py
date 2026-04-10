"""استثناهای سفارشی"""

class AccountReceiverError(Exception):
    """خطای پایه برای رسیور اکانت"""
    pass

class InvalidCredentialsError(AccountReceiverError):
    """خطای اطلاعات نامعتبر"""
    pass

class LoginFailedError(AccountReceiverError):
    """خطای شکست در ورود"""
    pass

class SessionSaveError(AccountReceiverError):
    """خطای ذخیره سشن"""
    pass
