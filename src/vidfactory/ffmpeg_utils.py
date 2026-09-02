"""FFmpeg / ffprobe helpers.

FFmpeg is the only rendering engine used by this project. It is free, it is
already available on GitHub Actions runners (and installed by the workflow if
not), and it can do everything this pipeline needs.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .logging_utils import get_logger

log = get_logger("FFMPEG")


class FFmpegError(RuntimeError):
    """Raised when an FFmpeg or ffprobe invocation fails."""


def ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_path() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def ffmpeg_available() -> bool:
    """True when both ffmpeg and ffprobe can be executed."""

    for binary in (ffmpeg_path(), ffprobe_path()):
        if shutil.which(binary) is None and not Path(binary).exists():
            return False
    try:
        subprocess.run(
            [ffmpeg_path(), "-version"],
            capture_output=True,
            check=True,
            timeout=30,
        )
        subprocess.run(
            [ffprobe_path(), "-version"],
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-version"], capture_output=True, text=True, timeout=30
        )
        return result.stdout.splitlines()[0] if result.stdout else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def run_ffmpeg(
    args: Sequence[str],
    timeout: float = 3600.0,
    description: str = "ffmpeg",
) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg with sane defaults, raising :class:`FFmpegError` on failure."""

    command = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    log.debug("%s: %s", description, " ".join(command))
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"{description} timed out after {timeout:.0f}s") from exc
    except OSError as exc:
        raise FFmpegError(f"{description} could not start: {exc}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()
        tail = "\n".join(stderr[-8:]) if stderr else "no stderr"
        raise FFmpegError(f"{description} failed (exit {result.returncode}):\n{tail}")
    return result


@dataclass
class MediaInfo:
    """Normalized ffprobe output for one media file."""

    path: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_video: bool = False
    has_audio: bool = False
    video_codec: str = ""
    audio_codec: str = ""
    sample_rate: int = 0
    channels: int = 0
    size_bytes: int = 0
    nb_frames: int = 0

    @property
    def aspect_ratio(self) -> float:
        return (self.width / self.height) if self.height else 0.0

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "duration": round(self.duration, 3),
            "width": self.width,
            "height": self.height,
            "fps": round(self.fps, 3),
            "has_video": self.has_video,
            "has_audio": self.has_audio,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "size_bytes": self.size_bytes,
        }


def _parse_fraction(value: Any) -> float:
    try:
        text = str(value)
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else 0.0
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def probe_media(path: str | Path, timeout: float = 120.0) -> MediaInfo:
    """Run ffprobe and return a :class:`MediaInfo`. Never raises for bad files."""

    target = Path(path)
    info = MediaInfo(path=str(target))
    if not target.exists():
        return info
    info.size_bytes = target.stat().st_size

    command = [
        ffprobe_path(),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(target),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        if result.returncode != 0:
            log.debug("ffprobe failed for %s: %s", target.name, (result.stderr or "").strip()[:200])
            return info
        payload = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        log.debug("ffprobe error for %s: %s", target.name, exc)
        return info

    fmt = payload.get("format") or {}
    info.duration = float(fmt.get("duration") or 0.0)

    for stream in payload.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "video" and not info.has_video:
            info.has_video = True
            info.width = int(stream.get("width") or 0)
            info.height = int(stream.get("height") or 0)
            info.fps = _parse_fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
            info.video_codec = str(stream.get("codec_name") or "")
            info.nb_frames = int(stream.get("nb_frames") or 0)
            if not info.duration:
                info.duration = float(stream.get("duration") or 0.0)
        elif kind == "audio" and not info.has_audio:
            info.has_audio = True
            info.audio_codec = str(stream.get("codec_name") or "")
            info.sample_rate = int(stream.get("sample_rate") or 0)
            info.channels = int(stream.get("channels") or 0)
            if not info.duration:
                info.duration = float(stream.get("duration") or 0.0)

    return info


def media_duration(path: str | Path) -> float:
    return probe_media(path).duration


def is_valid_video(
    path: str | Path,
    min_duration: float = 0.5,
    min_width: int = 16,
) -> bool:
    """Cheap integrity check for a downloaded or rendered clip."""

    info = probe_media(path)
    return bool(
        info.has_video
        and info.duration >= min_duration
        and info.width >= min_width
        and info.height >= min_width
        and info.size_bytes > 1024
    )


def make_silence(destination: str | Path, seconds: float, sample_rate: int = 48000) -> Path:
    """Generate a silent WAV of an exact length (used for narration pacing)."""

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=mono:sample_rate={int(sample_rate)}",
            "-t", f"{max(seconds, 0.01):.3f}",
            "-c:a", "pcm_s16le",
            str(target),
        ],
        description="silence",
    )
    return target


def concat_audio(parts: Sequence[str | Path], destination: str | Path, sample_rate: int = 48000) -> Path:
    """Concatenate WAV parts losslessly through the concat demuxer."""

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    listing = target.with_suffix(".concat.txt")
    with open(listing, "w", encoding="utf-8") as handle:
        for part in parts:
            resolved = str(Path(part).resolve()).replace("'", r"'\''")
            handle.write(f"file '{resolved}'\n")
    run_ffmpeg(
        [
            "-f", "concat",
            "-safe", "0",
            "-i", str(listing),
            "-ar", str(int(sample_rate)),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(target),
        ],
        description="audio concat",
    )
    listing.unlink(missing_ok=True)
    return target


def format_timestamp(seconds: float, separator: str = ",") -> str:
    """Format seconds as ``HH:MM:SS,mmm`` (SRT) or ``HH:MM:SS.mmm`` (ASS/ffmpeg)."""

    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def format_chapter(seconds: float) -> str:
    """Format seconds as a YouTube chapter timestamp (``M:SS`` or ``H:MM:SS``)."""

    total = max(0, int(float(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"
