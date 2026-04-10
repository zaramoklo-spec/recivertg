# راهنمای استفاده

## استفاده از طریق ربات

### 1. شروع کار

در تلگرام ربات را پیدا کرده و دستور `/start` را ارسال کنید.

### 2. ارسال شماره تلفن

شماره تلفن خود را با فرمت بین‌المللی ارسال کنید:

```
+989123456789
```

### 3. ارسال کد تایید

کد 5 رقمی که از تلگرام دریافت کردید را ارسال کنید:

```
12345
```

### 4. رمز دو مرحله‌ای (اختیاری)

اگر رمز دو مرحله‌ای دارید، آن را ارسال کنید. در غیر این صورت `/skip` را ارسال کنید.

### 5. تکمیل

سشن شما در پوشه `sessions` ذخیره می‌شود.

## استفاده به صورت ماژول

```python
import asyncio
from src.services import AccountReceiver
from src.models import AccountCredentials

async def main():
    # ایجاد نمونه
    receiver = AccountReceiver()
    
    # تعریف اطلاعات ورود
    credentials = AccountCredentials(
        phone="+989123456789",
        code="12345",
        password="my_password"  # اختیاری
    )
    
    # ورود به اکانت
    result = await receiver.login_account(credentials)
    
    if result.success:
        print(f"✅ ورود موفق!")
        print(f"شناسه کاربر: {result.user_id}")
        print(f"نام کاربری: @{result.username}")
        print(f"مسیر سشن: {result.session_path}")
    else:
        print(f"❌ خطا: {result.message}")

if __name__ == '__main__':
    asyncio.run(main())
```

## بارگذاری سشن ذخیره شده

```python
from src.services import AccountReceiver

async def load_saved_session():
    receiver = AccountReceiver()
    
    # بارگذاری سشن
    client = await receiver.load_session('sessions/989123456789_123456789.session')
    
    # استفاده از کلاینت
    me = await client.get_me()
    print(f"وارد شدید به عنوان: {me.first_name}")
    
    # قطع اتصال
    await client.disconnect()

asyncio.run(load_saved_session())
```

## دستورات ربات

- `/start` - شروع فرآیند ورود
- `/cancel` - لغو عملیات جاری
- `/skip` - رد کردن رمز دو مرحله‌ای
