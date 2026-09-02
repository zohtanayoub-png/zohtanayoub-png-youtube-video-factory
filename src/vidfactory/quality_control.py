"""Post-render validation with ffprobe.

The GitHub Action must fail loudly when the output is not a usable video, so
every check below is explicit and every failure is reported with the actual
measured value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .ffmpeg_utils import MediaInfo, probe_media
from .logging_utils import get_logger

log = get_logger("QC")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"      # error | warning

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass
class QualityReport:
    checks: list[Check] = field(default_factory=list)
    info: MediaInfo | None = None

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "media": self.info.to_dict() if self.info else {},
        }

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return target

    def log_summary(self) -> None:
        for check in self.checks:
            if check.passed:
                log.debug("PASS %s %s", check.name, check.detail)
            elif check.severity == "warning":
                log.warning("%s: %s", check.name, check.detail)
            else:
                log.error("%s: %s", check.name, check.detail)
        if self.passed:
            log.info(
                "Video validated (%s, %.1fs, %.1f MB)",
                self.info.resolution if self.info else "?",
                self.info.duration if self.info else 0.0,
                (self.info.size_bytes / 1_000_000) if self.info else 0.0,
            )
        else:
            log.error("%d validation failure(s)", len(self.failures))


def validate_output(
    video_path: str | Path,
    expected_duration: float,
    expected_width: int = 1920,
    expected_height: int = 1080,
    expected_fps: int = 30,
    min_file_mb: float = 1.0,
    duration_tolerance: float = 12.0,
    subtitles_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
    subtitles_required: bool = True,
) -> QualityReport:
    """Run every output check and return a structured report."""

    path = Path(video_path)
    report = QualityReport()

    exists = path.exists()
    report.checks.append(
        Check("file_exists", exists, f"{path}" if exists else f"{path} is missing")
    )
    if not exists:
        report.log_summary()
        return report

    info = probe_media(path)
    report.info = info

    size_mb = info.size_bytes / 1_000_000
    report.checks.append(
        Check(
            "file_size",
            size_mb >= min_file_mb,
            f"{size_mb:.2f} MB (minimum {min_file_mb:.2f} MB)",
        )
    )
    report.checks.append(
        Check("video_stream", info.has_video, f"codec={info.video_codec or 'none'}")
    )
    report.checks.append(
        Check("audio_stream", info.has_audio, f"codec={info.audio_codec or 'none'}")
    )
    report.checks.append(
        Check(
            "video_duration",
            info.duration > 0.5,
            f"{info.duration:.2f}s",
        )
    )
    report.checks.append(
        Check(
            "resolution",
            info.width == expected_width and info.height == expected_height,
            f"{info.resolution} (expected {expected_width}x{expected_height})",
        )
    )
    report.checks.append(
        Check(
            "frame_rate",
            abs(info.fps - expected_fps) < 1.0,
            f"{info.fps:.2f} fps (expected {expected_fps})",
            severity="warning",
        )
    )
    report.checks.append(
        Check(
            "codec_h264",
            info.video_codec in ("h264", "libx264"),
            f"video codec is {info.video_codec or 'unknown'}",
        )
    )
    report.checks.append(
        Check(
            "codec_aac",
            info.audio_codec in ("aac", "mp4a"),
            f"audio codec is {info.audio_codec or 'unknown'}",
        )
    )

    if expected_duration > 0:
        delta = abs(info.duration - expected_duration)
        report.checks.append(
            Check(
                "duration_matches_narration",
                delta <= duration_tolerance,
                f"video {info.duration:.1f}s vs narration {expected_duration:.1f}s "
                f"(delta {delta:.1f}s, tolerance {duration_tolerance:.1f}s)",
            )
        )

    if subtitles_path is not None:
        subtitle_file = Path(subtitles_path)
        has_content = subtitle_file.exists() and subtitle_file.stat().st_size > 16
        report.checks.append(
            Check(
                "subtitles_generated",
                has_content,
                f"{subtitle_file.name}" if has_content else f"{subtitle_file} missing or empty",
                severity="error" if subtitles_required else "warning",
            )
        )

    if metadata_path is not None:
        metadata_file = Path(metadata_path)
        valid = False
        detail = f"{metadata_file} missing"
        if metadata_file.exists():
            try:
                payload = json.loads(metadata_file.read_text(encoding="utf-8"))
                valid = bool(payload.get("title")) and bool(payload.get("description"))
                detail = f"title and description present" if valid else "title or description empty"
            except json.JSONDecodeError as exc:
                detail = f"invalid JSON: {exc}"
        report.checks.append(Check("metadata_generated", valid, detail))

    report.log_summary()
    return report


def has_black_start(video_path: str | Path, sample_seconds: float = 2.0) -> bool:
    """Detect an all-black opening, which usually means a broken first shot."""

    from .ffmpeg_utils import ffmpeg_path
    import subprocess

    try:
        result = subprocess.run(
            [
                ffmpeg_path(),
                "-hide_banner",
                "-nostdin",
                "-t", f"{sample_seconds:.2f}",
                "-i", str(video_path),
                "-vf", "blackdetect=d=0.5:pix_th=0.10",
                "-an",
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "black_start:0" in (result.stderr or "")
