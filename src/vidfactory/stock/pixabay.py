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
PHOTO_URL = "https://pixabay.com/api/"

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
    def search_images(self, query: str, per_page: int = 20, **filters: Any) -> list[StockClip]:
        """Photographs, from the same key and the same licence as the videos."""

        if not self.available:
            raise ProviderError("PIXABAY_API_KEY is not set")

        self.throttle()
        payload = request_json(
            PHOTO_URL,
            params={
                "key": self.api_key,
                "q": query,
                "per_page": max(3, min(int(per_page), 200)),
                "page": max(1, int(filters.get("page", 1))),
                "image_type": "photo",
                "safesearch": "true",
            },
            retries=int(filters.get("retries", 3)),
            timeout=float(filters.get("timeout", 30.0)),
        )
        return self.parse_photos(payload, query)

    # ------------------------------------------------------------------
    @classmethod
    def parse_photos(cls, payload: dict[str, Any], query: str = "") -> list[StockClip]:
        clips: list[StockClip] = []
        for hit in (payload or {}).get("hits", []) or []:
            link = str(hit.get("largeImageURL") or hit.get("webformatURL") or "")
            if not link:
                continue
            tags = [t.strip() for t in str(hit.get("tags", "")).split(",") if t.strip()]
            clips.append(
                StockClip(
                    provider=cls.name,
                    provider_id=f"photo-{hit.get('id', '')}",
                    download_url=link,
                    width=int(hit.get("imageWidth") or 0),
                    height=int(hit.get("imageHeight") or 0),
                    duration=0.0,
                    page_url=str(hit.get("pageURL", "")),
                    author=str(hit.get("user", "")),
                    license_name=cls.license_name,
                    preview_image=str(hit.get("webformatURL") or link),
                    preview_images=[str(hit.get("webformatURL") or link)],
                    query=query,
                    tags=tags,
                    media_type="image",
                )
            )
        return [clip for clip in clips if clip.provider_id and clip.download_url]

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
                    # Pixabay publishes one still per rendition rather than a
                    # timeline of them, so frame inspection falls back to
                    # decoding the video itself for these clips.
                    preview_image=str(best.get("thumbnail", "")),
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
