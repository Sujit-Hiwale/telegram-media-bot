import asyncio
import os
import re
import shutil
from PIL import Image

from telegram import Update, InputMediaPhoto, InputMediaVideo
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

# Maximum number of downloads happening at once.
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)

# Don't upload too many large files to Telegram simultaneously.
UPLOAD_SEMAPHORE = asyncio.Semaphore(2)


def get_media_type(filename):
    extension = os.path.splitext(filename)[1].lower()

    if extension in IMAGE_EXTENSIONS:
        return "image"

    if extension in VIDEO_EXTENSIONS:
        return "video"

    return "document"

def _prepare_image(filename):
    extension = os.path.splitext(filename)[1].lower()

    if extension in {".jpg", ".jpeg", ".png"}:
        return filename

    converted = os.path.splitext(filename)[0] + ".jpg"

    with Image.open(filename) as img:
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, "white")
            background.paste(img, mask=img.getchannel("A"))
            img = background
        else:
            img = img.convert("RGB")

        img.save(converted, "JPEG", quality=92)

    return converted

async def _send_single_media(update, filename, title):
    media_type = get_media_type(filename)

    if media_type == "image":
        filename = _prepare_image(filename)

    size_mb = os.path.getsize(filename) / (1024 * 1024)

    async with UPLOAD_SEMAPHORE:
        with open(filename, "rb") as media:

            if media_type == "image":
                sent = await update.message.reply_photo(
                    photo=media,
                    caption=f"📷 {title}",
                    read_timeout=60,
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=60,
                )

            elif media_type == "video":
                sent = await update.message.reply_video(
                    video=media,
                    caption=f"🎬 {title}",
                    read_timeout=60,
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=60,
                    supports_streaming=True,
                )

            else:
                sent = await update.message.reply_document(
                    document=media,
                    caption=f"📁 {title}",
                    read_timeout=60,
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=60,
                )

    return sent, size_mb

async def _send_media_group(update, filenames, title):
    """
    Sends Instagram carousel images/videos as a Telegram media group.
    Telegram allows up to 10 items in one media group.
    """

    media_group = []
    opened_files = []

    try:
        for index, filename in enumerate(filenames[:10]):

            media_type = get_media_type(filename)

            # Telegram media groups support photos and videos.
            if media_type == "image":
                filename = _prepare_image(filename)
                file_object = open(filename, "rb")
                opened_files.append(file_object)

                media_group.append(
                    InputMediaPhoto(
                        media=file_object,
                        caption=f"📷 {title}" if index == 0 else None,
                    )
                )

            elif media_type == "video":
                file_object = open(filename, "rb")
                opened_files.append(file_object)

                media_group.append(
                    InputMediaVideo(
                        media=file_object,
                        caption=f"🎬 {title}" if index == 0 else None,
                        supports_streaming=True,
                    )
                )

        if not media_group:
            raise RuntimeError("No supported media found.")

        async with UPLOAD_SEMAPHORE:
            sent_messages = await update.message.reply_media_group(
                media=media_group,
                read_timeout=60,
                write_timeout=300,
                connect_timeout=60,
                pool_timeout=60,
            )

        return sent_messages

    finally:
        for file_object in opened_files:
            try:
                file_object.close()
            except Exception:
                pass


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    text = update.message.text

    match = URL_PATTERN.search(text)

    if not match:
        return

    url = match.group(0).rstrip(".,!?)]}")

    context.chat_data.setdefault(
        "user_messages",
        []
    ).append(update.message.message_id)

    status = await update.message.reply_text(
        "🔎 Processing URL..."
    )

    context.chat_data.setdefault(
        "bot_messages",
        []
    ).append(status.message_id)

    temp_dir = None

    try:

        await status.edit_text(
            "🔎 Processing URL...\n\n"
            "Checking the media source..."
        )

        # ---------------------------------------------------------
        # LIMIT CONCURRENT DOWNLOADS
        # ---------------------------------------------------------

        if DOWNLOAD_SEMAPHORE.locked():

            await status.edit_text(
                "⏳ You're in the download queue...\n\n"
                "Another download is currently being processed."
            )

        async with DOWNLOAD_SEMAPHORE:

            await status.edit_text(
                "⬇️ Downloading...\n\n"
                "Please wait."
            )

            media_files, title, temp_dir = await asyncio.to_thread(
                download_media,
                url
            )

        if not media_files:
            raise RuntimeError(
                "Downloader returned no media."
            )

        # ---------------------------------------------------------
        # VALIDATE FILES
        # ---------------------------------------------------------

        valid_files = []

        for filename in media_files:

            if not os.path.isfile(filename):
                continue

            if os.path.getsize(filename) == 0:
                continue

            valid_files.append(filename)

        if not valid_files:
            raise RuntimeError(
                "Downloaded files were empty."
            )

        total_size = sum(
            os.path.getsize(filename)
            for filename in valid_files
        )

        total_size_mb = total_size / (1024 * 1024)

        await status.edit_text(
            f"✅ Media found\n\n"
            f"📄 {title}\n"
            f"📦 {total_size_mb:.1f} MB\n"
            f"📁 {len(valid_files)} file(s)\n\n"
            f"📤 Sending..."
        )

        # ---------------------------------------------------------
        # SINGLE FILE
        # ---------------------------------------------------------

        if len(valid_files) == 1:

            sent, _ = await _send_single_media(
                update,
                valid_files[0],
                title
            )

            if sent:
                if isinstance(sent, list):
                    for message in sent:
                        context.chat_data.setdefault(
                            "bot_messages",
                            []
                        ).append(message.message_id)

                else:
                    context.chat_data.setdefault(
                        "bot_messages",
                        []
                    ).append(sent.message_id)

        # ---------------------------------------------------------
        # MULTIPLE FILES
        # ---------------------------------------------------------

        else:

            sent_messages = await _send_media_group(
                update,
                valid_files,
                title
            )

            for message in sent_messages:

                context.chat_data.setdefault(
                    "bot_messages",
                    []
                ).append(message.message_id)

            if len(valid_files) > 10:

                await update.message.reply_text(
                    f"⚠️ This post contained {len(valid_files)} "
                    f"items. Telegram media groups support up to "
                    f"10 items, so only the first 10 were sent."
                )

        await status.delete()

    except Exception as error:

        print(
            f"[DOWNLOAD ERROR] {url}\n"
            f"{type(error).__name__}: {error}"
        )

        try:

            await status.edit_text(
                "❌ I couldn't download this media.\n\n"
                "The website may be blocking automated downloads, "
                "the media may require login, or the URL may have "
                "expired."
            )

        except Exception:
            pass

    finally:

        if temp_dir:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )