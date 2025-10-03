FROM python:3.10-slim

# نصب ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# تنظیم پوشه کاری
WORKDIR /app

# کپی فایل‌های پروژه
COPY . .

# نصب پکیج‌ها
RUN pip install --no-cache-dir -r requirements.txt

# اجرای بات
CMD ["python", "bot.py"]
