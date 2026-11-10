import os
import re
import shutil
import tempfile
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import yt_dlp


IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/avif",
    "image/heic",
    "image/heif",
    "image/jxl",
}

VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
    "video/x-msvideo",
    "video/mpeg",
    "video/3gpp",
}


def _safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return name[:150] or "media"


def _extension_from_content_type(content_type):
    content_type = content_type.split(";")[0].lower()

    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/avif": ".avif",
        "image/heic": ".heic",
        "image/heif": ".heif",
        "image/jxl": ".jxl",

        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
        "video/x-matroska": ".mkv",
        "video/x-msvideo": ".avi",
        "video/mpeg": ".mpeg",
        "video/3gpp": ".3gp",
    }

    return mapping.get(content_type)


def _download_direct(url, temp_dir):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 Chrome/147 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        stream=True,
        timeout=(20, 60),
        allow_redirects=True,
    )

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    content_type = content_type.split(";")[0]

    extension = _extension_from_content_type(content_type)

    if content_type not in IMAGE_CONTENT_TYPES | VIDEO_CONTENT_TYPES:
        response.close()
        return None

    if not extension:
        extension = ".bin"

    filename = os.path.join(
        temp_dir,
        f"downloaded_media{extension}"
    )

    with open(filename, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                file.write(chunk)

    return filename, "Downloaded media"


def _extract_web_media(url, temp_dir):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 Chrome/147 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=(20, 60),
    )

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()

    if "text/html" not in content_type:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # OpenGraph image
    for meta in soup.find_all("meta"):
        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        value = meta.get("content")

        if not value:
            continue

        if prop in {
            "og:image",
            "twitter:image",
            "twitter:image:src",
        }:
            media_url = urljoin(url, value)

            try:
                result = _download_direct(
                    media_url,
                    temp_dir
                )

                if result:
                    filename, _ = result
                    return filename, "Downloaded image"

            except Exception:
                pass

    # OpenGraph video
    for meta in soup.find_all("meta"):
        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        value = meta.get("content")

        if prop in {
            "og:video",
            "og:video:url",
            "og:video:secure_url",
            "twitter:player:stream",
        } and value:

            media_url = urljoin(url, value)

            try:
                result = _download_direct(
                    media_url,
                    temp_dir
                )

                if result:
                    filename, _ = result
                    return filename, "Downloaded video"

            except Exception:
                pass

    # <img>
    for image in soup.find_all("img"):
        media_url = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-lazy-src")
        )

        if not media_url:
            continue

        media_url = urljoin(url, media_url)

        try:
            result = _download_direct(
                media_url,
                temp_dir
            )

            if result:
                filename, _ = result
                return filename, "Downloaded image"

        except Exception:
            pass

    # <video> / <source>
    for video in soup.find_all(["video", "source"]):
        media_url = (
            video.get("src")
            or video.get("data-src")
        )

        if not media_url:
            continue

        media_url = urljoin(url, media_url)

        try:
            result = _download_direct(
                media_url,
                temp_dir
            )

            if result:
                filename, _ = result
                return filename, "Downloaded video"

        except Exception:
            pass

    return None


def _download_with_ytdlp(url, temp_dir):
    options = {
        "outtmpl": os.path.join(
            temp_dir,
            "%(title).150s.%(ext)s"
        ),

        "format": "bestvideo*+bestaudio/best",

        "noplaylist": True,

        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "socket_timeout": 30,

        "source_address": "0.0.0.0",

        "merge_output_format": "mp4",

        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            url,
            download=True
        )

    files = [
        os.path.join(temp_dir, name)
        for name in os.listdir(temp_dir)
        if os.path.isfile(
            os.path.join(temp_dir, name)
        )
    ]

    if not files:
        raise RuntimeError(
            "No media file was downloaded."
        )

    filename = max(
        files,
        key=os.path.getsize
    )

    title = info.get(
        "title",
        "Downloaded media"
    )

    return filename, title


def download_media(url: str):
    temp_dir = tempfile.mkdtemp(
        prefix="telegram-media-"
    )

    try:
        # 1. Direct image/video URL
        try:
            result = _download_direct(url, temp_dir)

            if result:
                return result[0], result[1], temp_dir

        except Exception:
            pass

        # 2. Use yt-dlp for known video/social platforms first
        try:
            filename, title = _download_with_ytdlp(
                url,
                temp_dir
            )

            return filename, title, temp_dir

        except Exception:
            pass

        # 3. Generic webpage extraction
        try:
            result = _extract_web_media(
                url,
                temp_dir
            )

            if result:
                return result[0], result[1], temp_dir

        except Exception:
            pass

        raise RuntimeError(
            "This website did not expose a downloadable "
            "image or video."
        )

    except Exception:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )
        raise