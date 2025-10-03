# bot.py
import os
import yt_dlp
import glob
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # از Variables در Railway بخونده میشه
# اختیاری: اگر می‌خوای یوتیوب با کوکی کار کنه، محتوای cookies.txt رو در یک متغیر محیطی بذار:
# YT_COOKIES_CONTENT (میتونی بعداً بذاری؛ الان لازم نیست)
YT_COOKIES_CONTENT = os.getenv("YT_COOKIES_CONTENT")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _prepare_mp3_name(ydl, info):
    # yt-dlp.prepare_filename ممکنه پس‌پردازش رو بازتاب نده؛ پس مبتنی بر نام پایه فایل mp3 برمی‌گردونیم
    fname = ydl.prepare_filename(info)
    base = os.path.splitext(fname)[0]
    return base + ".mp3"


def _write_cookies_file_if_needed():
    """اگر YT_COOKIES_CONTENT ست شده، یک فایل cookies.txt می‌سازد و مسیرش را برمی‌گرداند"""
    if not YT_COOKIES_CONTENT:
        return None
    path = os.path.join(DOWNLOAD_DIR, "yt_cookies.txt")
    # اگر متغیر محیطی با \n فرستاده شده باشد، تبدیلش کن
    content = YT_COOKIES_CONTENT.replace("\\n", "\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _download_with_ydl(query, source="sc", cookiefile=None):
    """
    source: "sc" (SoundCloud) یا "yt" (YouTube)
    برمی‌گرداند: (local_filepath, info_dict)
    ممکنه Exception بندازه که بالاتر هندل می‌کنیم.
    """
    if source == "sc":
        default_search = "scsearch1"
    else:
        default_search = "ytsearch1"

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "default_search": default_search,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        # تا حدی خطایابی بهتر باشد می‌توان 'verbose': True گذاشت ولی در سرور لاگ زیاد می‌شود
    }

    # SoundCloud: لازم است extract_flat=False تا لینک واقعی رو دنبال کنه
    if source == "sc":
        ydl_opts["extract_flat"] = False

    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        # اگر search برگردوند، اولین مورد را بگیر
        if isinstance(info, dict) and info.get("entries"):
            info = info["entries"][0]
        # آماده‌سازی اسم خروجی (پس‌پردازش ممکنه پسوند رو عوض کنه)
        mp3_path = _prepare_mp3_name(ydl, info)
        if not os.path.exists(mp3_path):
            # fallback: جدیدترین mp3 در پوشه دانلود
            files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.mp3"))
            if files:
                mp3_path = max(files, key=os.path.getctime)
            else:
                raise FileNotFoundError("بعد از دانلود فایل mp3 پیدا نشد.")
        return mp3_path, info


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! اسم آهنگ یا خواننده رو بفرست تا برات MP3 بیارم 🎧")


async def search_and_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    if not query:
        await update.message.reply_text("لطفاً اسم آهنگ یا خواننده را بفرست.")
        return

    msg = await update.message.reply_text("🔎 دارم سرچ می‌کنم...")

    cookiefile = _write_cookies_file_if_needed()  # اگر YT_COOKIES_CONTENT ست باشه فایل می‌سازه

    # 1) تلاش اول: SoundCloud
    try:
        mp3_path, info = _download_with_ydl(query, source="sc", cookiefile=None)
        source_name = "SoundCloud"
    except Exception as sc_e:
        logger.warning("SoundCloud failed: %s", sc_e)
        # اگر خطا مربوط به extractor باشه یا محدودیت، میریم سراغ یوتیوب
        try:
            mp3_path, info = _download_with_ydl(query, source="yt", cookiefile=cookiefile)
            source_name = "YouTube"
        except Exception as yt_e:
            logger.error("YouTube fallback failed: %s", yt_e)
            # اگر پیام مخصوص یوتیوب بخواد کوکی (Sign in to confirm) اطلاع بدیم به کاربر
            txt = str(yt_e)
            if "Sign in to confirm" in txt or "cookies" in txt.lower():
                await msg.edit_text(
                    "❌ یوتیوب برای این ویدیو نیاز به کوکی داره (پیغام: Sign in to confirm). "
                    "اگر مایل هستی می‌تونی فایل cookies.txt مرورگرت رو استخراج کنی و محتویاتش رو "
                    "در متغیر محیطی `YT_COOKIES_CONTENT` قرار بدی (راهنما پایین)."
                )
            else:
                await msg.edit_text(f"❌ دانلود ناموفق شد:\nSoundCloud error: {sc_e}\nYouTube error: {yt_e}")
            return

    # ارسال فایل به کاربر
    try:
        title = info.get("title") or os.path.basename(mp3_path)
        performer = info.get("uploader") or info.get("artist") or None
        await msg.edit_text(f"✅ پیدا شد از: {source_name} — دارم آپلود می‌کنم...")
        with open(mp3_path, "rb") as f:
            await update.message.reply_audio(audio=f, title=title, performer=performer)
    except Exception as send_e:
        await msg.edit_text(f"❌ مشکل در ارسال فایل: {send_e}")
        logger.exception(send_e)
    finally:
        # پاکسازی فایل محلی
        try:
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
            if cookiefile and os.path.exists(cookiefile):
                os.remove(cookiefile)
        except Exception:
            pass


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_and_download))
    app.run_polling()


if __name__ == "__main__":
    main()
