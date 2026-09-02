"""Pexels video adapter.

API docs: https://www.pexels.com/api/documentation/#videos
Pexels content is free to use, modification is allowed and attribution is
appreciated but not required. We record attribution anyway.
"""

from __future__ import annotations

import os
from typing import Any

from ..http import request_json
from ..logging_utils import get_logger
from .base import ProviderError, StockClip, StockProvider

log = get_logger("PEXELS")

API_URL = "https://api.pexels.com/videos/search"


class PexelsProvider(StockProvider):
    name = "pexels"
    license_name = "Pexels License (free to use, no attribution required)"

    def __init__(self, api_key: str | None = None, **options: Any) -> None:
        super().__init__(api_key or os.environ.get("PEXELS_API_KEY", ""), **options)

    # ------------------------------------------------------------------
    def search(self, query: str, per_page: int = 20, **filters: Any) -> list[StockClip]:
        if not self.available:
            raise ProviderError("PEXELS_API_KEY is not set")

        self.throttle()
        payload = request_json(
            API_URL,
            headers={"Authorization": self.api_key},
            params={
                "query": query,
                "per_page": max(1, min(int(per_page), 80)),
                "orientation": filters.get("orientation", "landscape"),
                "size": filters.get("size", "medium"),
            },
            retries=int(filters.get("retries", 3)),
            timeout=float(filters.get("timeout", 30.0)),
        )
        return self.parse(payload, query)

    # ------------------------------------------------------------------
    @classmethod
    def parse(cls, payload: dict[str, Any], query: str = "") -> list[StockClip]:
        """Convert a Pexels API response into :class:`StockClip` records."""

        clips: list[StockClip] = []
        for video in (payload or {}).get("videos", []) or []:
            best = cls._best_file(video.get("video_files") or [])
            if best is None:
                continue
            user = video.get("user") or {}
            clips.append(
                StockClip(
                    provider=cls.name,
                    provider_id=str(video.get("id", "")),
                    download_url=str(best.get("link", "")),
                    width=int(best.get("width") or video.get("width") or 0),
                    height=int(best.get("height") or video.get("height") or 0),
                    duration=float(video.get("duration") or 0.0),
                    page_url=str(video.get("url", "")),
                    author=str(user.get("name", "")),
                    author_url=str(user.get("url", "")),
                    license_name=cls.license_name,
                    preview_image=str(video.get("image", "")),
                    file_size=int(best.get("file_size") or 0),
                    query=query,
                )
            )
        return [clip for clip in clips if clip.provider_id and clip.download_url]

    #: We render at 1080p, so anything wider is wasted bandwidth and wasted
    #: decode time on a two-core runner.
    TARGET_WIDTH = 1920

    @classmethod
    def _best_file(cls, files: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Pick the smallest MP4 rendition that is still at least 1080p wide.

        Pexels returns several renditions of the same clip, often including 4K.
        Downloading the 4K version of 150 clips would cost gigabytes of transfer
        and a large amount of decode time for no visible benefit in a 1080p
        render, so the smallest rendition at or above 1920 wide wins.
        """

        usable = [
            f
            for f in files
            if str(f.get("file_type", "")).endswith("mp4") and int(f.get("width") or 0) > 0
        ]
        if not usable:
            return None
        big_enough = [f for f in usable if int(f["width"]) >= cls.TARGET_WIDTH]
        if big_enough:
            return min(big_enough, key=lambda f: int(f.get("width") or 0))
        return max(usable, key=lambda f: int(f.get("width") or 0))
