import os
import json
import math
import time
import asyncio
import subprocess
from pyrogram.types import Message

ACTIVE_TASKS: dict[str, dict] = {}

LANG_NAMES = {
    "eng": "English",
    "en": "English",
    "hin": "Hindi",
    "hi": "Hindi",
    "tel": "Telugu",
    "te": "Telugu",
    "tam": "Tamil",
    "ta": "Tamil",
    "mal": "Malayalam",
    "ml": "Malayalam",
    "kan": "Kannada",
    "kn": "Kannada",
    "ben": "Bengali",
    "bn": "Bengali",
    "mar": "Marathi",
    "mr": "Marathi",
    "jpn": "Japanese",
    "ja": "Japanese",
    "kor": "Korean",
    "ko": "Korean",
    "spa": "Spanish",
    "es": "Spanish",
    "fre": "French",
    "fra": "French",
    "fr": "French",
    "ger": "German",
    "deu": "German",
    "de": "German",
    "ara": "Arabic",
    "ar": "Arabic",
    "rus": "Russian",
    "ru": "Russian",
    "und": "Unknown",
}

def format_language(lang_code: str | None) -> str:
    if not lang_code:
        return "Unknown"
    code = lang_code.strip().lower()
    return LANG_NAMES.get(code, code.upper())

def human_bytes(size: float) -> str:
    if not size:
        return "0 B"
    power = 1024
    n = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    while size >= power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def human_time(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

async def progress_bar(current: int, total: int, message: Message, start_time: float, action: str, gid: str):
    if gid not in ACTIVE_TASKS:
        raise asyncio.CancelledError("Task cancelled by user.")

    now = time.time()
    diff = now - start_time
    last_edit = ACTIVE_TASKS[gid].get("last_edit", 0)

    if (now - last_edit) >= 4.0 or current == total:
        ACTIVE_TASKS[gid]["last_edit"] = now
        percentage = (current * 100 / total) if total > 0 else 0
        speed = (current / diff) if diff > 0 else 0
        eta = round((total - current) / speed) if speed > 0 else 0

        filled = math.floor(percentage / 10)
        bar = "█" * filled + "░" * (10 - filled)

        text = (
            f"**{action}**\n"
            f"`[{bar}]` **{percentage:.1f}%**\n"
            f"**Processed:** `{human_bytes(current)}` / `{human_bytes(total)}`\n"
            f"**Speed:** `{human_bytes(speed)}/s` | **ETA:** `{human_time(eta)}`\n"
            f"**Cancel:** `/cancel {gid}`"
        )
        try:
            await message.edit_text(text)
        except Exception:
            pass

def inspect_media_file(file_path: str) -> dict:
    """
    Detects file type (video/audio/document), extracts duration & resolution,
    formats all audio tracks with language + codec (e.g. 'English (AAC), Hindi (AC3)'),
    and generates a thumbnail when possible.
    """
    info = {
        "kind": "document",
        "duration": 0,
        "width": 0,
        "height": 0,
        "audio_summary": "None",
        "thumb": None,
    }

    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", file_path
        ]
        raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
        data = json.loads(raw)
        streams = data.get("streams", [])
        fmt = data.get("format", {})

        dur_raw = fmt.get("duration") or 0
        info["duration"] = int(float(dur_raw)) if dur_raw else 0

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        if audio_streams:
            tracks = []
            for a_stream in audio_streams:
                codec = (a_stream.get("codec_name") or "Audio").upper()
                tags = a_stream.get("tags") or {}
                lang = format_language(tags.get("language") or tags.get("lang"))
                tracks.append(f"{lang} ({codec})")
            info["audio_summary"] = ", ".join(tracks)

        if video_stream:
            codec = (video_stream.get("codec_name") or "").lower()
            w = int(video_stream.get("width") or 0)
            h = int(video_stream.get("height") or 0)

            is_attached_cover = (
                codec in ("mjpeg", "png", "bmp", "webp")
                and info["duration"] > 0
                and not audio_streams
            )
            if w > 0 and h > 0 and not is_attached_cover:
                info["kind"] = "video"
                info["width"] = w
                info["height"] = h
                if not info["duration"] and video_stream.get("duration"):
                    info["duration"] = int(float(video_stream["duration"]))

                thumb_path = f"{file_path}_thumb.jpg"
                ss = max(1, info["duration"] // 2) if info["duration"] > 2 else 0
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-ss", str(ss), "-i", file_path,
                        "-vframes", "1", "-vf", "scale=320:-1", "-q:v", "3", thumb_path
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                    info["thumb"] = thumb_path

        if info["kind"] != "video" and audio_streams:
            info["kind"] = "audio"
            if not info["duration"] and audio_streams[0].get("duration"):
                info["duration"] = int(float(audio_streams[0]["duration"]))

            thumb_path = f"{file_path}_audio_thumb.jpg"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", file_path,
                    "-an", "-vcodec", "mjpeg", "-vf", "scale=320:-1", "-q:v", "3", thumb_path
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                info["thumb"] = thumb_path

    except Exception:
        pass

    return info

def split_large_file(file_path: str, chunk_size_mb: int = 1950) -> list[str]:
    output_prefix = f"{file_path}.7z"
    cmd = ["7z", "a", "-mx=0", f"-v{chunk_size_mb}m", output_prefix, file_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    directory = os.path.dirname(file_path)
    base_name = os.path.basename(output_prefix)
    return sorted([
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.startswith(base_name)
    ])
