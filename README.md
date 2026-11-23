# ایجنت اینستاگرام با گزارش روزانه تلگرام

ایجنتی که هر روز آمار اینستاگرام شما را جمع می‌کند، با Claude تحلیل می‌کند، پست جدید پیشنهاد می‌دهد (با کپشن و هشتگ آماده)، برای کامنت‌ها پاسخ پیشنهاد می‌کند و گزارش را به تلگرام می‌فرستد. هر گزارش به‌صورت فایل هم در چت تلگرام ذخیره می‌شود. از تلگرام می‌توانید پیش‌نویس‌ها را با تأیید خودتان منتشر کنید.

طراحی کامل، محدودیت‌ها و نقشه راه (واتساپ و بقیه سرویس‌ها): [docs/DESIGN.md](docs/DESIGN.md)

## چه چیزهایی لازم است

1. **حساب اینستاگرام Business یا Creator** که به یک صفحه فیسبوک وصل باشد.
2. **یک اپ در [Meta for Developers](https://developers.facebook.com/)** با محصول Instagram Graph API و مجوزهای `instagram_basic`، `instagram_manage_insights`، `instagram_manage_comments`، `instagram_content_publish`، `pages_show_list`. از آن یک **توکن بلندمدت** و **شناسه کاربر اینستاگرام** (`IG_USER_ID`) می‌گیرید.
3. **ربات تلگرام**: در تلگرام به `@BotFather` پیام بدهید، `/newbot` بزنید و توکن را بگیرید. بعد یک پیام به ربات خودتان بفرستید و شناسه چت را از `https://api.telegram.org/bot<TOKEN>/getUpdates` بردارید.
4. **کلید API Claude** از [console.anthropic.com](https://console.anthropic.com/).

## راه‌اندازی محلی

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # مقادیر را پر کنید؛ این فایل commit نمی‌شود
python -m agent check  # تست اتصال اینستاگرام و تلگرام
python -m agent daily  # ساخت و ارسال گزارش همین الان
python -m agent bot --daily-at 09:00  # ربات تعاملی + گزارش خودکار ساعت ۹
```

## دو روش اجرا

- **روش ۱ (پیشنهادی): ربات روی یک سیستم همیشه‌روشن** (یک VPS کوچک، رزبری‌پای یا کامپیوتر خانه) با `python -m agent bot --daily-at 09:00`. هم گزارش روزانه می‌فرستد و هم دستورات انتشار و پاسخ کامنت کار می‌کنند.
- **روش ۲: فقط گزارش، بدون سرور** با GitHub Actions (پایین). گزارش و پیش‌نویس‌ها می‌رسند، ولی دستورات `/publish` و `/reply` فقط وقتی کار می‌کنند که ربات (روش ۱) هم روشن باشد، چون پیش‌نویس‌ها در دیتابیس همان سیستم ذخیره می‌شوند.

## اجرای خودکار روزانه با GitHub Actions

در تنظیمات ریپو، بخش **Settings → Secrets and variables → Actions** این Secretها را اضافه کنید:
`ANTHROPIC_API_KEY`، `IG_USER_ID`، `IG_ACCESS_TOKEN`، `TELEGRAM_BOT_TOKEN`، `TELEGRAM_CHAT_ID`.
اختیاری (در تب Variables): `ACCOUNT_BRIEF` (توضیح کوتاه درباره پیج شما)، `IG_GRAPH_HOST`.

گزارش هر روز ساعت ۹ صبح به وقت تهران ارسال می‌شود. برای اجرای دستی: تب **Actions → Daily Instagram report → Run workflow**.

## دستورات ربات تلگرام

| دستور | کار |
|---|---|
| `/report` | ساخت گزارش همین الان |
| `/drafts` | فهرست پیش‌نویس‌ها |
| `/draft 3` | متن کامل پیش‌نویس ۳ |
| `/publish 3 https://…/photo.jpg` | پیش‌نمایش انتشار پیش‌نویس ۳ با این عکس |
| `/confirm 3` | انتشار نهایی در اینستاگرام |
| `/reply <comment_id> متن` | پاسخ به کامنت |

> Claude متن و ایده می‌سازد، نه عکس. برای انتشار، لینک عمومی (https) عکس را خودتان می‌دهید.

## تست

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
