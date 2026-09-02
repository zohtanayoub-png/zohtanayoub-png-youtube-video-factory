"""Clip downloading: retries, validation, hashing and duplicate rejection.

Downloads are the least reliable step in the pipeline, so every clip is
validated with ffprobe after fetching and a bad clip is simply dropped. The
renderer is designed to work with fewer clips than requested, so a handful of
failures degrades quality slightly rather than failing the whole render.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .ffmpeg_utils import probe_media
from .http import HttpError, download_file
from .logging_utils import get_logger
from .stock.base import StockClip

log = get_logger("DOWNLOAD")


def content_hash(path: str | Path, sample_bytes: int = 2_000_000) -> str:
    """Cheap file fingerprint: size plus a hash of the head and tail bytes.

    Hashing an entire 60 MB video is wasteful; head+tail+size catches exact
    duplicate downloads (the same asset served under two different IDs), which
    is the case we actually need to detect.
    """

    target = Path(path)
    if not target.exists():
        return ""
    size = target.stat().st_size
    digest = hashlib.sha256()
    digest.update(str(size).encode("ascii"))
    with open(target, "rb") as handle:
        digest.update(handle.read(sample_bytes))
        if size > sample_bytes * 2:
            handle.seek(-sample_bytes, 2)
            digest.update(handle.read(sample_bytes))
    return digest.hexdigest()


@dataclass
class DownloadResult:
    clip: StockClip
    path: Path
    duration: float
    width: int
    height: int

    @property
    def ok(self) -> bool:
        return self.path.exists() and self.duration > 0


class ClipDownloader:
    """Fetches, validates and de-duplicates stock clips into a working folder."""

    def __init__(
        self,
        workdir: str | Path,
        min_width: int = 1280,
        min_height: int = 720,
        min_seconds: float = 3.0,
        max_mb: float = 90.0,
        timeout: float = 120.0,
        retries: int = 3,
        known_hashes: Iterable[str] = (),
    ) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.min_width = int(min_width)
        self.min_height = int(min_height)
        self.min_seconds = float(min_seconds)
        self.max_bytes = int(max_mb * 1_000_000)
        self.timeout = float(timeout)
        self.retries = int(retries)
        self.seen_hashes: set[str] = {h for h in known_hashes if h}
        self.failures = 0

    # ------------------------------------------------------------------
    def target_path(self, clip: StockClip) -> Path:
        safe_id = "".join(ch for ch in str(clip.provider_id) if ch.isalnum() or ch in "-_")
        return self.workdir / f"{clip.provider}_{safe_id}.mp4"

    def fetch(self, clip: StockClip) -> DownloadResult | None:
        """Download and validate one clip. Returns ``None`` when unusable."""

        target = self.target_path(clip)

        try:
            if clip.local_path:
                # Local provider: copy rather than download.
                source = Path(clip.local_path)
                if not source.exists():
                    raise HttpError(f"local clip missing: {source}")
                if target.resolve() != source.resolve():
                    shutil.copy2(source, target)
            elif not target.exists():
                download_file(
                    clip.download_url,
                    target,
                    retries=self.retries,
                    timeout=self.timeout,
                    max_bytes=self.max_bytes,
                )
        except Exception as exc:
            self.failures += 1
            log.warning("Skipping %s: %s", clip.key, exc)
            target.unlink(missing_ok=True)
            return None

        info = probe_media(target)
        if not info.has_video or info.duration <= 0:
            self.failures += 1
            log.warning("Skipping %s: downloaded file is not a usable video", clip.key)
            target.unlink(missing_ok=True)
            return None
        if info.width < self.min_width or info.height < self.min_height:
            self.failures += 1
            log.warning(
                "Skipping %s: %s is below the %dx%d minimum",
                clip.key,
                info.resolution,
                self.min_width,
                self.min_height,
            )
            target.unlink(missing_ok=True)
            return None
        if info.duration < self.min_seconds:
            self.failures += 1
            log.warning(
                "Skipping %s: %.1fs is shorter than the %.1fs minimum",
                clip.key,
                info.duration,
                self.min_seconds,
            )
            target.unlink(missing_ok=True)
            return None

        digest = content_hash(target)
        if digest and digest in self.seen_hashes:
            log.info("Skipping %s: byte-identical to a clip already downloaded", clip.key)
            target.unlink(missing_ok=True)
            return None
        if digest:
            self.seen_hashes.add(digest)

        clip.local_path = str(target)
        clip.content_hash = digest
        clip.width = info.width or clip.width
        clip.height = info.height or clip.height
        clip.duration = info.duration or clip.duration

        return DownloadResult(
            clip=clip,
            path=target,
            duration=info.duration,
            width=info.width,
            height=info.height,
        )

    # ------------------------------------------------------------------
    def fetch_many(self, clips: Sequence[StockClip], needed: int | None = None) -> list[DownloadResult]:
        """Download clips in order until ``needed`` succeed or the list runs out."""

        results: list[DownloadResult] = []
        for clip in clips:
            if needed is not None and len(results) >= needed:
                break
            result = self.fetch(clip)
            if result is not None:
                results.append(result)
        if self.failures:
            log.info("%d clip(s) were rejected or failed to download", self.failures)
        return results

    def cleanup(self) -> None:
        """Remove the working folder (called after a successful render)."""

        shutil.rmtree(self.workdir, ignore_errors=True)
