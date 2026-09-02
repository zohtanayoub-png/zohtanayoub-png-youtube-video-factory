"""Pixabay video adapter.

API docs: https://pixabay.com/api/docs/#api_search_videos
Pixabay content is free to use under the Pixabay Content License.
"""

from __future__ import annotations

import os
from typing import Any

from ..http import request_json
from ..logging_utils import get_logger
from .base import ProviderError, StockClip, StockProvider

log = get_logger("PIXABAY")

API_URL = "https://pixabay.com/api/videos/"

#: Rendition names in descending quality order.
_RENDITIONS = ("large", "medium", "small", "tiny")


class PixabayProvider(StockProvider):
    name = "pixabay"
    license_name = "Pixabay Content License (free to use, no attribution required)"

    def __init__(self, api_key: str | None = None, **options: Any) -> None:
        super().__init__(api_key or os.environ.get("PIXABAY_API_KEY", ""), **options)

    # ------------------------------------------------------------------
    def search(self, query: str, per_page: int = 20, **filters: Any) -> list[StockClip]:
        if not self.available:
            raise ProviderError("PIXABAY_API_KEY is not set")

        self.throttle()
        payload = request_json(
            API_URL,
            params={
                "key": self.api_key,
                "q": query,
                # Pixabay rejects per_page below 3.
                "per_page": max(3, min(int(per_page), 200)),
                "page": max(1, int(filters.get("page", 1))),
                "video_type": "all",
                "safesearch": "true",
            },
            retries=int(filters.get("retries", 3)),
            timeout=float(filters.get("timeout", 30.0)),
        )
        return self.parse(payload, query)

    # ------------------------------------------------------------------
    @classmethod
    def parse(cls, payload: dict[str, Any], query: str = "") -> list[StockClip]:
        clips: list[StockClip] = []
        for hit in (payload or {}).get("hits", []) or []:
            videos = hit.get("videos") or {}
            best = cls._best_file(videos)
            if best is None:
                continue
            tags = [t.strip() for t in str(hit.get("tags", "")).split(",") if t.strip()]
            clips.append(
                StockClip(
                    provider=cls.name,
                    provider_id=str(hit.get("id", "")),
                    download_url=str(best.get("url", "")),
                    width=int(best.get("width") or 0),
                    height=int(best.get("height") or 0),
                    duration=float(hit.get("duration") or 0.0),
                    page_url=str(hit.get("pageURL", "")),
                    author=str(hit.get("user", "")),
                    author_url=(
                        f"https://pixabay.com/users/{hit.get('user', '')}-{hit.get('user_id', '')}/"
                        if hit.get("user")
                        else ""
                    ),
                    license_name=cls.license_name,
                    file_size=int(best.get("size") or 0),
                    query=query,
                    tags=tags,
                    description=" ".join(tags),
                )
            )
        return [clip for clip in clips if clip.provider_id and clip.download_url]

    @staticmethod
    def _best_file(videos: dict[str, Any]) -> dict[str, Any] | None:
        for name in _RENDITIONS:
            entry = videos.get(name) or {}
            if entry.get("url") and int(entry.get("width") or 0) > 0:
                return entry
        return None
