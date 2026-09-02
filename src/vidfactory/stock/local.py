"""Local footage adapter for media you own or have permission to use.

This is also what the offline integration test uses: it serves synthetic
clips generated with FFmpeg so the whole pipeline can be exercised with no
API credentials and no network access.

Drop ``.mp4`` files into ``assets/local_clips/`` and enable ``sources.local``
in ``config.yaml``. Filenames become the searchable text, so
``cozy-living-room-curtains.mp4`` is matched by a curtains query.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..ffmpeg_utils import probe_media
from ..logging_utils import get_logger
from .base import StockClip, StockProvider

log = get_logger("LOCAL")

DEFAULT_DIRECTORY = Path("assets/local_clips")
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


class LocalProvider(StockProvider):
    name = "local"
    license_name = "Supplied by the channel owner"
    min_interval = 0.0

    def __init__(self, api_key: str | None = None, **options: Any) -> None:
        super().__init__(api_key or "local", **options)
        directory = options.get("directory") or os.environ.get(
            "VIDFACTORY_LOCAL_CLIPS", str(DEFAULT_DIRECTORY)
        )
        self.directory = Path(directory)
        self._catalog: list[StockClip] | None = None

    @property
    def available(self) -> bool:
        return self.directory.is_dir() and any(
            p.suffix.lower() in VIDEO_SUFFIXES for p in self.directory.iterdir()
        )

    # ------------------------------------------------------------------
    def catalog(self) -> list[StockClip]:
        if self._catalog is not None:
            return self._catalog

        clips: list[StockClip] = []
        if self.directory.is_dir():
            for path in sorted(self.directory.iterdir()):
                if path.suffix.lower() not in VIDEO_SUFFIXES:
                    continue
                info = probe_media(path)
                if not info.has_video:
                    log.warning("Skipping %s: no video stream", path.name)
                    continue
                clips.append(
                    StockClip(
                        provider=self.name,
                        provider_id=path.stem,
                        download_url=str(path.resolve()),
                        width=info.width,
                        height=info.height,
                        duration=info.duration,
                        page_url=str(path.resolve()),
                        author="local",
                        license_name=self.license_name,
                        local_path=str(path.resolve()),
                        tags=sorted(_words(path.stem)),
                    )
                )
        self._catalog = clips
        return clips

    # ------------------------------------------------------------------
    def search(self, query: str, per_page: int = 20, **filters: Any) -> list[StockClip]:
        query_words = _words(query)
        scored: list[tuple[float, StockClip]] = []
        for clip in self.catalog():
            overlap = len(query_words & set(clip.tags))
            # Everything stays reachable so the pipeline never starves, but
            # filename matches sort first.
            scored.append((overlap, clip))
        scored.sort(key=lambda pair: -pair[0])

        results: list[StockClip] = []
        for _, clip in scored[: max(1, per_page)]:
            copy = StockClip(**{**clip.__dict__})
            copy.query = query
            results.append(copy)
        return results
