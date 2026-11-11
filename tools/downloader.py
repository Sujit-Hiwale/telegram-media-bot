import html
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import yt_dlp


# ============================================================
# CONSTANTS
# ============================================================

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

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

MAX_GOOGLE_IMAGES = 10


# ============================================================
# HTTP
# ============================================================

def _session(referer=None):
    session = requests.Session()

    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })

    if referer:
        session.headers["Referer"] = referer

    return session


# ============================================================
# HELPERS
# ============================================================

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


def _is_valid_file(path):
    return (
        os.path.isfile(path)
        and os.path.getsize(path) > 0
    )


def _collect_files(directory):
    files = []

    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            path = os.path.join(root, filename)

            if _is_valid_file(path):
                files.append(path)

    files.sort()

    return files


def _host(url):
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )
    except Exception:
        return ""


# ============================================================
# PLATFORM DETECTION
# ============================================================

def _is_instagram(url):
    host = _host(url)

    return (
        host == "instagram.com"
        or host.endswith(".instagram.com")
    )


def _is_google_images(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    query = parse_qs(parsed.query)

    return (
        (
            host == "google.com"
            or host.endswith(".google.com")
        )
        and (
            query.get("tbm", [""])[0] == "isch"
            or "/search" in parsed.path
            and "q" in query
        )
    )


def _is_youtube(url):
    host = _host(url)

    return (
        "youtube.com" in host
        or host == "youtu.be"
    )


def _is_facebook(url):
    host = _host(url)

    return (
        "facebook.com" in host
        or host == "fb.watch"
    )


def _is_x(url):
    host = _host(url)

    return (
        host == "x.com"
        or host.endswith(".x.com")
        or host == "twitter.com"
        or host.endswith(".twitter.com")
    )


def _is_reddit(url):
    host = _host(url)

    return (
        host == "reddit.com"
        or host.endswith(".reddit.com")
        or host == "redd.it"
    )


def _is_sharechat(url):
    host = _host(url)

    return (
        "sharechat.com" in host
    )


# ============================================================
# DIRECT MEDIA DOWNLOAD
# ============================================================

def _download_direct(url, temp_dir, referer=None):
    session = _session(referer)

    try:
        response = session.get(
            url,
            stream=True,
            timeout=(20, 90),
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
            .split(";")[0]
        )

        if (
            content_type not in IMAGE_CONTENT_TYPES
            and content_type not in VIDEO_CONTENT_TYPES
        ):
            return None

        extension = _extension_from_content_type(
            content_type
        )

        if not extension:
            return None

        filename = os.path.join(
            temp_dir,
            f"media_{len(os.listdir(temp_dir))}{extension}"
        )

        with open(filename, "wb") as file:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    file.write(chunk)

        if not _is_valid_file(filename):
            try:
                os.remove(filename)
            except OSError:
                pass

            return None

        return filename

    finally:
        response.close()
        session.close()


# ============================================================
# INSTAGRAM
# ============================================================

def _download_instagram(url, temp_dir):
    """
    Instagram downloader.

    Uses parth-dl instead of gallery-dl.

    This supports public:
        - image posts
        - video posts
        - reels
        - carousels

    No Chrome login/cookies required.
    """

    executable = shutil.which("parth-dl")

    if not executable:
        raise RuntimeError(
            "parth-dl is not installed. "
            "Run: pip install -U parth-dl"
        )

    # parth-dl writes into the current directory.
    # Use the temporary directory as cwd so all files
    # stay isolated and are cleaned automatically.
    result = subprocess.run(
        [
            executable,
            url,
        ],
        cwd=temp_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )

    print("[PARTH-DL]")
    print(result.stdout)

    if result.returncode != 0:
        print("[PARTH-DL ERROR]")
        print(result.stderr)

        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "parth-dl failed"
        )

    files = _collect_files(temp_dir)

    if not files:
        raise RuntimeError(
            "parth-dl completed but returned no media."
        )

    print(
        f"[INSTAGRAM] "
        f"Downloaded {len(files)} file(s)"
    )

    return files


# ============================================================
# GOOGLE IMAGES
# ============================================================

def _clean_google_url(value):
    """
    Google embeds URLs in escaped HTML/JSON.
    Clean them before downloading.
    """

    value = html.unescape(value)

    value = value.replace(
        "\\/",
        "/"
    )

    value = value.replace(
        "\\u003d",
        "="
    )

    value = value.replace(
        "\\u0026",
        "&"
    )

    value = value.replace(
        "\\u003F",
        "?"
    )

    value = value.strip(
        "\"'()[]{}"
    )

    return value


def _looks_like_image_url(url):
    if not url.startswith(("http://", "https://")):
        return False

    lower = url.lower()

    # Ignore Google's own thumbnail/cache services.
    blocked_hosts = (
        "gstatic.com",
        "google.com",
        "googleusercontent.com",
    )

    host = _host(url)

    if any(
        host == item
        or host.endswith("." + item)
        for item in blocked_hosts
    ):
        return False

    image_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".bmp",
        ".avif",
    )

    if any(
        ext in lower
        for ext in image_extensions
    ):
        return True

    # Many real image URLs have no extension.
    return True


def _extract_google_image_urls(page_url, html_text):
    """
    Extract likely original image URLs from Google Images'
    HTML/embedded data.

    This deliberately avoids Google's thumbnail URLs.
    """

    results = []

    # --------------------------------------------------------
    # Method 1: normal HTML attributes
    # --------------------------------------------------------

    soup = BeautifulSoup(
        html_text,
        "html.parser"
    )

    for tag in soup.find_all(
        ["img", "a"]
    ):

        for attribute in (
            "src",
            "data-src",
            "href",
        ):

            value = tag.get(attribute)

            if not value:
                continue

            value = _clean_google_url(
                value
            )

            if _looks_like_image_url(value):

                if value not in results:
                    results.append(value)

    # --------------------------------------------------------
    # Method 2: embedded JSON / script URLs
    # --------------------------------------------------------

    pattern = re.compile(
        r'https?://[^"\'\\\s<>]+'
    )

    for match in pattern.finditer(
        html_text
    ):

        value = _clean_google_url(
            match.group(0)
        )

        if not _looks_like_image_url(value):
            continue

        if value not in results:
            results.append(value)

    return results


def _download_google_images(url, temp_dir):
    session = _session(
        "https://www.google.com/"
    )

    try:
        response = session.get(
            url,
            timeout=(20, 60),
        )

        response.raise_for_status()

        image_urls = _extract_google_image_urls(
            url,
            response.text
        )

        if not image_urls:
            raise RuntimeError(
                "Google Images did not expose image URLs."
            )

        files = []

        for image_url in image_urls:

            if len(files) >= MAX_GOOGLE_IMAGES:
                break

            try:

                filename = _download_direct(
                    image_url,
                    temp_dir,
                    referer=url
                )

                if filename:
                    files.append(filename)

            except Exception as error:

                print(
                    f"[GOOGLE IMAGE FAILED] "
                    f"{image_url}: "
                    f"{type(error).__name__}: {error}"
                )

                continue

        if not files:
            raise RuntimeError(
                "Could not download any Google Images."
            )

        print(
            f"[GOOGLE IMAGES] "
            f"Downloaded {len(files)} image(s)"
        )

        return files

    finally:
        session.close()


# ============================================================
# YT-DLP
# ============================================================

def _download_with_ytdlp(url, temp_dir):
    """
    Handles:
        YouTube
        Facebook
        X/Twitter
        Reddit
        ShareChat
        and many other supported sites.
    """

    ffmpeg = shutil.which("ffmpeg")

    options = {
        "outtmpl": os.path.join(
            temp_dir,
            "%(title).150s.%(ext)s"
        ),

        "noplaylist": True,

        "retries": 4,
        "fragment_retries": 4,
        "extractor_retries": 3,

        "socket_timeout": 30,

        "quiet": True,
        "no_warnings": True,

        "ignoreerrors": False,

        # Don't download an entire playlist when a URL
        # happens to point into one.
        "playlistend": 1,

        # Prefer sane filenames.
        "restrictfilenames": True,
    }

    # --------------------------------------------------------
    # FFmpeg available
    # --------------------------------------------------------

    if ffmpeg:

        options["format"] = (
            "bv*[height<=480]+ba/"
            "b[height<=480]/"
            "b"
        )

        options["merge_output_format"] = "mp4"

        options["ffmpeg_location"] = (
            os.path.dirname(ffmpeg)
        )

    # --------------------------------------------------------
    # No FFmpeg
    # --------------------------------------------------------

    else:

        options["format"] = (
            "b[ext=mp4]/"
            "b"
        )

    # --------------------------------------------------------
    # Optional cookies
    #
    # NOT required for public content.
    #
    # Can be used later for sites that require login.
    # --------------------------------------------------------

    cookies_file = os.getenv(
        "YTDLP_COOKIES"
    )

    if (
        cookies_file
        and os.path.isfile(cookies_file)
    ):
        options["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(
        options
    ) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

    if not info:
        raise RuntimeError(
            "yt-dlp returned no media information."
        )

    files = _collect_files(
        temp_dir
    )

    if not files:
        raise RuntimeError(
            "yt-dlp did not create a media file."
        )

    # --------------------------------------------------------
    # Prefer final merged media over intermediate files.
    # --------------------------------------------------------

    preferred = [
        file
        for file in files
        if os.path.splitext(file)[1].lower()
        in {
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }
    ]

    if preferred:
        files = preferred

    filename = max(
        files,
        key=os.path.getsize
    )

    title = (
        info.get("title")
        or info.get("fulltitle")
        or "Downloaded media"
    )

    print(
        f"[YT-DLP] "
        f"{title} -> {filename}"
    )

    return [filename], title


# ============================================================
# GENERIC HTML EXTRACTION
# ============================================================

def _extract_web_media(url, temp_dir):
    session = _session()

    try:

        response = session.get(
            url,
            timeout=(20, 60),
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
        )

        if "text/html" not in content_type:
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # OpenGraph
        # ----------------------------------------------------

        image_properties = {
            "og:image",
            "og:image:url",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
        }

        video_properties = {
            "og:video",
            "og:video:url",
            "og:video:secure_url",
            "twitter:player:stream",
        }

        # Images first
        for meta in soup.find_all("meta"):

            prop = (
                meta.get("property")
                or meta.get("name")
                or ""
            ).lower()

            value = meta.get("content")

            if (
                not value
                or prop not in image_properties
            ):
                continue

            media_url = urljoin(
                url,
                value
            )

            try:

                filename = _download_direct(
                    media_url,
                    temp_dir,
                    referer=url
                )

                if filename:
                    return [filename]

            except Exception:
                continue

        # Videos
        for meta in soup.find_all("meta"):

            prop = (
                meta.get("property")
                or meta.get("name")
                or ""
            ).lower()

            value = meta.get("content")

            if (
                not value
                or prop not in video_properties
            ):
                continue

            media_url = urljoin(
                url,
                value
            )

            try:

                filename = _download_direct(
                    media_url,
                    temp_dir,
                    referer=url
                )

                if filename:
                    return [filename]

            except Exception:
                continue

        # ----------------------------------------------------
        # IMG
        # ----------------------------------------------------

        for image in soup.find_all("img"):

            media_url = (
                image.get("src")
                or image.get("data-src")
                or image.get("data-lazy-src")
            )

            if not media_url:
                continue

            media_url = urljoin(
                url,
                media_url
            )

            try:

                filename = _download_direct(
                    media_url,
                    temp_dir,
                    referer=url
                )

                if filename:
                    return [filename]

            except Exception:
                continue

        # ----------------------------------------------------
        # VIDEO / SOURCE
        # ----------------------------------------------------

        for video in soup.find_all(
            ["video", "source"]
        ):

            media_url = (
                video.get("src")
                or video.get("data-src")
            )

            if not media_url:
                continue

            media_url = urljoin(
                url,
                media_url
            )

            try:

                filename = _download_direct(
                    media_url,
                    temp_dir,
                    referer=url
                )

                if filename:
                    return [filename]

            except Exception:
                continue

        return None

    finally:
        session.close()


# ============================================================
# MAIN DOWNLOAD ROUTER
# ============================================================

def download_media(url: str):

    temp_dir = tempfile.mkdtemp(
        prefix="telegram-media-"
    )

    try:

        # ====================================================
        # 1. DIRECT IMAGE / VIDEO
        # ====================================================

        try:

            filename = _download_direct(
                url,
                temp_dir
            )

            if filename:

                return (
                    [filename],
                    "Downloaded media",
                    temp_dir
                )

        except Exception as error:

            print(
                f"[DIRECT FAILED] "
                f"{type(error).__name__}: {error}"
            )

        # ====================================================
        # 2. INSTAGRAM
        # ====================================================

        if _is_instagram(url):

            try:

                files = _download_instagram(
                    url,
                    temp_dir
                )

                return (
                    files,
                    "Instagram media",
                    temp_dir
                )

            except Exception as error:

                print(
                    f"[INSTAGRAM FAILED] "
                    f"{type(error).__name__}: {error}"
                )

        # ====================================================
        # 3. GOOGLE IMAGES
        # ====================================================

        if _is_google_images(url):

            try:

                files = _download_google_images(
                    url,
                    temp_dir
                )

                return (
                    files,
                    "Google Images",
                    temp_dir
                )

            except Exception as error:

                print(
                    f"[GOOGLE IMAGES FAILED] "
                    f"{type(error).__name__}: {error}"
                )

        # ====================================================
        # 4. YT-DLP SUPPORTED SOCIAL PLATFORMS
        # ====================================================

        platform = "website"

        if _is_youtube(url):
            platform = "YouTube"

        elif _is_facebook(url):
            platform = "Facebook"

        elif _is_x(url):
            platform = "X"

        elif _is_reddit(url):
            platform = "Reddit"

        elif _is_sharechat(url):
            platform = "ShareChat"

        try:

            files, title = _download_with_ytdlp(
                url,
                temp_dir
            )

            return (
                files,
                title,
                temp_dir
            )

        except Exception as error:
            print(f"[{platform}] yt-dlp unavailable, trying fallback...")

        # ====================================================
        # 5. GENERIC WEBPAGE FALLBACK
        # ====================================================

        try:

            files = _extract_web_media(
                url,
                temp_dir
            )

            if files:

                return (
                    files,
                    "Downloaded media",
                    temp_dir
                )

        except Exception as error:

            print(
                f"[HTML FALLBACK FAILED] "
                f"{type(error).__name__}: {error}"
            )

        raise RuntimeError(
            "No downloadable media was found."
        )

    except Exception:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        raise