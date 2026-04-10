# راهنمای نصب

## پیش‌نیازها

- Python 3.8 یا بالاتر
- pip (مدیر پکیج پایتون)

## مراحل نصب

### 1. کلون کردن پروژه

```bash
git clone <repository-url>
cd telegram-account-receiver
```

### 2. ایجاد محیط مجازی (توصیه می‌شود)

```bash
python -m venv venv

# در ویندوز
venv\Scripts\activate

# در لینوکس/مک
source venv/bin/activate
```

### 3. نصب وابستگی‌ها

```bash
pip install -r requirements.txt
```

### 4. تنظیمات

فایل `.env` را ایجاد کنید:

```bash
cp .env.example .env
```

اطلاعات زیر را در `.env` وارد کنید:

```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
SESSIONS_DIR=sessions
```

#### دریافت API_ID و API_HASH

1. به [my.telegram.org](https://my.telegram.org) بروید
2. وارد شوید
3. به بخش "API development tools" بروید
4. یک اپلیکیشن جدید بسازید
5. API_ID و API_HASH را کپی کنید

#### دریافت BOT_TOKEN

1. در تلگرام به [@BotFather](https://t.me/BotFather) بروید
2. دستور `/newbot` را ارسال کنید
3. نام و یوزرنیم ربات را وارد کنید
4. توکن دریافتی را کپی کنید

### 5. اجرای برنامه

```bash
python main.py
```

## عیب‌یابی

### خطای "No module named 'telethon'"

```bash
pip install --upgrade telethon
```

### خطای "Invalid API_ID or API_HASH"

- مطمئن شوید API_ID و API_HASH صحیح هستند
- فایل `.env` را بررسی کنید
