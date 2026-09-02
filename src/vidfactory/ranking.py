"""Clip scoring - never just take the first search result.

Every candidate returned by a provider is scored across six dimensions and
only clips above ``ranking.min_score`` are eligible. The weights are
configurable in ``config.yaml``.

======================  ======  =========================================
Dimension               Max     What it measures
======================  ======  =========================================
relevance               30      query / tag / filename word overlap
resolution              20      how close to (or above) 1920x1080
orientation             15      landscape and close to 16:9
duration                10      long enough for a 4-8 second shot
novelty                 15      never used before, or used long ago
quality                 10      sane frame rate, file size, provider signals
======================  ======  =========================================
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .logging_utils import get_logger
from .stock.base import StockClip

log = get_logger("RANKING")

DEFAULT_WEIGHTS: dict[str, float] = {
    "relevance": 30.0,
    "resolution": 20.0,
    "orientation": 15.0,
    "duration": 10.0,
    "novelty": 15.0,
    "quality": 10.0,
}

_STOP = {"the", "and", "for", "with", "interior", "home", "design", "video", "footage"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", str(text).lower()) if w not in _STOP}


# ---------------------------------------------------------------------------
# Individual scoring dimensions (each returns 0.0 - 1.0)
# ---------------------------------------------------------------------------

def score_relevance(clip: StockClip, query: str, keywords: Sequence[str] = ()) -> float:
    """Word overlap between the search intent and everything we know about a clip."""

    wanted = _words(query) | _words(" ".join(keywords))
    if not wanted:
        return 0.5
    haystack = _words(" ".join([clip.query, " ".join(clip.tags), clip.page_url, clip.provider_id]))
    if not haystack:
        # Providers like Pexels return no tags; the API already matched the
        # query, so credit a solid baseline rather than punishing the clip.
        return 0.62
    overlap = len(wanted & haystack)
    ratio = overlap / len(wanted)
    return min(1.0, 0.35 + 0.65 * ratio) if overlap else 0.3


def score_resolution(clip: StockClip, prefer_width: int = 1920, min_width: int = 1280) -> float:
    if clip.width <= 0 or clip.height <= 0:
        return 0.0
    if clip.width < min_width:
        return 0.05
    if clip.width >= prefer_width:
        # Above 1080p there is no benefit for a 1080p render, and 4K costs
        # download time and CPU, so the curve flattens rather than climbing.
        excess = min((clip.width - prefer_width) / prefer_width, 1.0)
        return 1.0 - 0.15 * excess
    return 0.45 + 0.5 * ((clip.width - min_width) / max(prefer_width - min_width, 1))


def score_orientation(clip: StockClip) -> float:
    ratio = clip.aspect_ratio
    if ratio <= 0:
        return 0.0
    if ratio < 1.0:
        # Vertical footage would have to be cropped destructively for 16:9.
        return 0.0
    target = 16 / 9
    deviation = abs(ratio - target) / target
    return max(0.0, 1.0 - deviation * 2.0)


def score_duration(clip: StockClip, min_shot: float = 4.0, max_shot: float = 8.0) -> float:
    duration = float(clip.duration or 0.0)
    if duration <= 0:
        return 0.3            # unknown; provider did not report it
    if duration < min_shot:
        return max(0.0, duration / min_shot * 0.6)
    if duration <= max_shot * 3:
        return 1.0
    # Very long clips are still usable (we take a section) but slower to fetch.
    return max(0.55, 1.0 - math.log10(duration / (max_shot * 3)) * 0.5)


def score_novelty(
    clip: StockClip,
    use_count: int = 0,
    days_since_use: float | None = None,
    cooldown_days: float = 45.0,
) -> float:
    if use_count <= 0:
        return 1.0
    if days_since_use is None:
        return 0.25
    if days_since_use < cooldown_days:
        return 0.0
    # Recovers slowly after the cooldown, and never fully for heavily used clips.
    recovery = min(1.0, (days_since_use - cooldown_days) / max(cooldown_days, 1.0))
    return max(0.0, (0.7 * recovery) / max(1, use_count))


def score_quality(clip: StockClip) -> float:
    value = 0.6
    if clip.file_size and clip.width:
        # Extremely small files at high resolution mean heavy compression.
        bytes_per_pixel_second = clip.file_size / max(
            clip.width * clip.height * max(clip.duration, 1.0), 1.0
        )
        if bytes_per_pixel_second < 0.005:
            value -= 0.25
        elif bytes_per_pixel_second > 0.02:
            value += 0.2
    if clip.author:
        value += 0.1
    if clip.preview_image or clip.page_url:
        value += 0.1
    if clip.duration >= 8:
        value += 0.1
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Ranking engine
# ---------------------------------------------------------------------------

@dataclass
class RankingContext:
    """Everything the ranker needs to know beyond the clip itself."""

    query: str = ""
    keywords: Sequence[str] = ()
    min_shot_seconds: float = 4.0
    max_shot_seconds: float = 8.0
    prefer_width: int = 1920
    min_width: int = 1280
    min_height: int = 720
    min_source_seconds: float = 3.0
    cooldown_days: float = 45.0
    #: ``{"provider:id": (use_count, days_since_last_use | None)}``
    history: Mapping[str, tuple[int, float | None]] = None  # type: ignore[assignment]
    #: Clips already chosen for this video; repeats are penalized hard.
    already_selected: Iterable[str] = ()

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = {}
        self.already_selected = set(self.already_selected or ())


class ClipRanker:
    """Scores and orders stock clip candidates."""

    def __init__(
        self,
        weights: Mapping[str, float] | None = None,
        min_score: float = 28.0,
        max_uses_per_clip: int = 3,
    ) -> None:
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self.min_score = float(min_score)
        self.max_uses_per_clip = int(max_uses_per_clip)

    # ------------------------------------------------------------------
    def score(self, clip: StockClip, context: RankingContext) -> tuple[float, dict[str, float]]:
        use_count, days_since = context.history.get(clip.key, (0, None))

        raw = {
            "relevance": score_relevance(clip, context.query, context.keywords),
            "resolution": score_resolution(clip, context.prefer_width, context.min_width),
            "orientation": score_orientation(clip),
            "duration": score_duration(clip, context.min_shot_seconds, context.max_shot_seconds),
            "novelty": score_novelty(clip, use_count, days_since, context.cooldown_days),
            "quality": score_quality(clip),
        }
        breakdown = {name: raw[name] * self.weights.get(name, 0.0) for name in raw}
        total = sum(breakdown.values())

        # Hard penalties applied after weighting.
        if clip.key in context.already_selected:
            total -= 40.0
            breakdown["repeat_penalty"] = -40.0
        if use_count >= self.max_uses_per_clip:
            total -= 30.0
            breakdown["overuse_penalty"] = -30.0
        if not clip.is_landscape:
            total -= 25.0
            breakdown["portrait_penalty"] = -25.0

        return round(total, 3), breakdown

    # ------------------------------------------------------------------
    @staticmethod
    def is_eligible(clip: StockClip, context: RankingContext) -> bool:
        """Hard requirements a clip must meet regardless of how it scores.

        These exist because a very small or very short clip can still collect
        enough points elsewhere to pass a score threshold, and neither can be
        used in a 1080p render without visible damage.
        """

        if clip.width < context.min_width or clip.height < context.min_height:
            return False
        if not clip.is_landscape:
            return False
        # A clip shorter than the minimum shot length cannot fill one shot.
        if clip.duration and clip.duration < min(
            context.min_source_seconds, context.min_shot_seconds
        ):
            return False
        return bool(clip.download_url)

    def rank(self, clips: Sequence[StockClip], context: RankingContext) -> list[StockClip]:
        """Return clips ordered best-first, dropping anything ineligible."""

        ranked: list[StockClip] = []
        for clip in clips:
            if not self.is_eligible(clip, context):
                continue
            total, breakdown = self.score(clip, context)
            clip.score = total
            clip.score_breakdown = breakdown
            if total >= self.min_score:
                ranked.append(clip)
        ranked.sort(key=lambda c: c.score, reverse=True)
        return ranked

    def rejected_count(self, clips: Sequence[StockClip], context: RankingContext) -> int:
        return len(clips) - len(self.rank(list(clips), context))


def diversify(clips: Sequence[StockClip], limit: int) -> list[StockClip]:
    """Pick top clips while avoiding several near-identical picks in a row.

    Providers frequently return sequential IDs from the same shoot, which look
    like the same footage. Spreading the selection across authors and ID ranges
    keeps a video from feeling repetitive.
    """

    chosen: list[StockClip] = []
    seen_authors: dict[str, int] = {}
    for clip in clips:
        if len(chosen) >= limit:
            break
        author = (clip.author or "").lower()
        if author and seen_authors.get(author, 0) >= max(2, limit // 4):
            continue
        if any(_looks_like_sibling(clip, other) for other in chosen):
            continue
        chosen.append(clip)
        if author:
            seen_authors[author] = seen_authors.get(author, 0) + 1

    # If diversification was too strict, top up from the ranked remainder.
    if len(chosen) < limit:
        keys = {c.key for c in chosen}
        for clip in clips:
            if len(chosen) >= limit:
                break
            if clip.key not in keys:
                chosen.append(clip)
                keys.add(clip.key)
    return chosen[:limit]


def _looks_like_sibling(a: StockClip, b: StockClip) -> bool:
    """Heuristic for two clips likely coming from the same upload batch."""

    if a.provider != b.provider or not a.author or a.author != b.author:
        return False
    try:
        return abs(int(a.provider_id) - int(b.provider_id)) <= 3
    except (TypeError, ValueError):
        return False
