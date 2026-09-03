"""Provider interface and the normalized clip record shared by all sources."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..logging_utils import get_logger

log = get_logger("STOCK")


class ProviderError(RuntimeError):
    """Raised when a provider cannot serve a request."""


@dataclass
class StockClip:
    """A single downloadable stock video candidate, normalized across sources.

    Attribution fields are always populated even where the license does not
    require credit, so ``video_sources.json`` can record exactly what was used.
    """

    provider: str
    provider_id: str
    download_url: str
    width: int
    height: int
    duration: float
    page_url: str = ""
    author: str = ""
    author_url: str = ""
    license_name: str = ""
    preview_image: str = ""
    #: Stills the provider publishes across the length of the video. Pexels
    #: gives about fifteen; they let the beginning, middle and end of a clip
    #: be inspected before a single frame of video is transferred.
    preview_images: list[str] = field(default_factory=list)
    file_size: int = 0
    query: str = ""
    tags: list[str] = field(default_factory=list)
    #: Human-readable description of the footage, where the provider gives one.
    #: Pexels has no tags field, but its page URL slug is a caption
    #: ("woman-cleaning-the-living-room"), which is a strong quality signal.
    description: str = ""
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    #: Unweighted stage-one dimensions, reused by the visual stage.
    score_dimensions: dict[str, float] = field(default_factory=dict)
    #: Why the aspirational score landed where it did, for the QC report.
    aspirational_reasons: list[str] = field(default_factory=list)
    #: Premium visual signals (people / empty / dark / interior relevance).
    premium: dict[str, Any] = field(default_factory=dict)
    #: What real frame inspection found, as a plain dict for the report.
    #: See :mod:`vidfactory.visual_analysis`.
    visual: dict[str, Any] = field(default_factory=dict)
    #: How well the frames match the sentence being narrated (0.0 - 1.0).
    visual_semantic_match: float = 0.0
    local_path: str = ""
    content_hash: str = ""

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.provider_id}"

    @property
    def aspect_ratio(self) -> float:
        return (self.width / self.height) if self.height else 0.0

    @property
    def content_text(self) -> str:
        """What the provider says this clip shows - evidence, not intent.

        Deliberately excludes the query we searched with: judging a clip by
        our own search string makes every result look relevant, because the
        words we were hoping for are in the text we are scoring.
        """

        return " ".join(
            part for part in (self.description, " ".join(self.tags)) if part
        ).strip().lower()

    @property
    def signal_text(self) -> str:
        """Everything known about the clip, including the query that found it."""

        return " ".join([self.description, " ".join(self.tags), self.query]).lower()

    @property
    def is_landscape(self) -> bool:
        return self.width >= self.height

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_id": self.provider_id,
            "page_url": self.page_url,
            "download_url": self.download_url,
            "width": self.width,
            "height": self.height,
            "duration": round(float(self.duration), 2),
            "author": self.author,
            "author_url": self.author_url,
            "description": self.description,
            "license": self.license_name,
            "query": self.query,
            "score": round(float(self.score), 2),
            "score_breakdown": {k: round(v, 2) for k, v in self.score_breakdown.items()},
            "aspirational_reasons": list(self.aspirational_reasons),
            "premium": dict(self.premium),
            "visual": dict(self.visual),
            "visual_semantic_match_score": round(float(self.visual_semantic_match), 3),
            "content_hash": self.content_hash,
        }


class StockProvider(ABC):
    """Base class for every stock footage source."""

    #: Short identifier stored in the database and in metadata.
    name: str = "base"
    #: Human-readable license summary recorded for attribution.
    license_name: str = ""
    #: Seconds to wait between API calls to stay polite with rate limits.
    min_interval: float = 0.34
    #: Whether asking for page 2+ can return anything new.
    supports_pagination: bool = True

    def __init__(self, api_key: str | None = None, **options: Any) -> None:
        self.api_key = api_key or ""
        self.options = options
        self._last_call = 0.0

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """Whether this provider can actually be used right now."""
        return bool(self.api_key)

    def throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    @abstractmethod
    def search(self, query: str, per_page: int = 20, **filters: Any) -> list[StockClip]:
        """Return normalized candidates for a single search query.

        ``filters`` may carry ``page`` so callers can go deeper than the first
        page of results when a query is productive but more variety is needed.
        """

    # ------------------------------------------------------------------
    def search_many(
        self, queries: Sequence[str], per_page: int = 20, **filters: Any
    ) -> list[StockClip]:
        """Search several queries, tolerating individual failures."""

        results: list[StockClip] = []
        seen: set[str] = set()
        for query in queries:
            try:
                for clip in self.search(query, per_page=per_page, **filters):
                    if clip.key not in seen:
                        seen.add(clip.key)
                        results.append(clip)
            except Exception as exc:
                log.warning("%s search failed for %r: %s", self.name, query, exc)
        return results
