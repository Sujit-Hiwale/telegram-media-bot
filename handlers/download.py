import asyncio
import os
import re
import shutil

from telegram import Update
from telegram.ext import ContextTypes

from tools.downloader import download_media


URL_PATTERN = re.compile(r"https?://\S+")

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".bmp", ".tif", ".tiff", ".avif",
    ".heic", ".heif", ".jxl"
}

VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".webm",
    ".mkv", ".avi", ".flv", ".wmv",
    ".3gp", ".ts"
}


def get_media_type(filename):
    extension = os.path.splitext(filename)[1].lower()

    if extension in IMAGE_EXTENSIONS:
        return "image"

    if extension in VIDEO_EXTENSIONS:
        return "video"

    return "document"


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""

    match = URL_PATTERN.search(text)

    if not match:
        return

    url = match.group(0).rstrip(".,!?)]}")

    status = await update.message.reply_text(
        "🔎 Processing URL..."
    )

    temp_dir = None

    try:
        await status.edit_text(
            "⬇️ Finding media...\n\n"
            "I’ll try to download the image or video from this link."
        )

        filename, title, temp_dir = await asyncio.to_thread(
            download_media,
            url
        )

        size_mb = os.path.getsize(filename) / (1024 * 1024)
        media_type = get_media_type(filename)

        await status.edit_text(
            f"✅ Media found\n\n"
            f"📄 {title}\n"
            f"📦 {size_mb:.1f} MB\n\n"
            f"📤 Sending..."
        )

        with open(filename, "rb") as media:

            if media_type == "image":
                await update.message.reply_photo(
                    photo=media,
                    caption=f"📷 {title}",
                    read_timeout=60,
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=60,
                )

            elif media_type == "video":
                await update.message.reply_video(
                    video=media,
                    caption=f"🎬 {title}",
                    read_timeout=60,
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=60,
                    supports_streaming=True,
                )

            else:
                await update.message.reply_document(
                    document=media,
                    caption=f"📁 {title}",
                    read_timeout=60,
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=60,
                )

        await status.delete()

    except Exception:
        await status.edit_text(
            "❌ I couldn't download this media.\n\n"
            "The website may be blocking downloads or the media "
            "may not be publicly accessible."
        )

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)