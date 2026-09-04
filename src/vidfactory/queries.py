"""Visual query construction.

Stock footage only illustrates the narration if the search terms describe what
the sentence is actually about. Settling for ``modern living room interior``
because it always returns results is how a video ends up looking like a random
Pexels compilation.

So every concept produces a ranked ladder of queries:

``specific``
    Hand-written for this exact idea ("floor to ceiling curtains living room").
``variant``
    The same subject framed differently - a close-up, a wide shot, a detail.
    This is also what lets one idea be illustrated by several complementary
    shots rather than four interchangeable wide rooms.
``broad``
    The subject with the room or style qualifier relaxed, for when the
    specific phrasing has no footage.
``generic``
    Category-level fallback. Always last, always flagged, and tracked in the
    editorial quality report so over-reliance on it is visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

SPECIFIC, VARIANT, BROAD, GENERIC = "specific", "variant", "broad", "generic"

#: Ranked best-first; ``specific`` is always attempted before ``generic``.
SPECIFICITY_ORDER = (SPECIFIC, VARIANT, BROAD, GENERIC)


@dataclass(frozen=True)
class VisualQuery:
    """One search string plus how specific it is to the narration."""

    text: str
    specificity: str = SPECIFIC
    #: "wide", "detail" or "" - used to build varied shot groups per idea.
    shot_type: str = ""

    @property
    def is_generic(self) -> bool:
        return self.specificity == GENERIC

    def to_dict(self) -> dict[str, str]:
        return {"text": self.text, "specificity": self.specificity, "shot_type": self.shot_type}


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Room words that can be relaxed to broaden an over-specific query.
ROOM_WORDS = (
    "living room", "bedroom", "kitchen", "bathroom", "dining room", "hallway",
    "entryway", "apartment", "home", "house", "interior", "room",
)

#: Framing modifiers. Mixing these is what produces wide/detail shot groups.
DETAIL_MODIFIERS = ("close up", "detail")
WIDE_MODIFIERS = ("wide shot", "spacious")

#: Words that describe the look we want and that stock captions actually use.
QUALITY_MODIFIERS = (
    "natural light",
    "styled",
    "modern",
    "bright",
)

#: Whole phrases rather than single modifiers, for when the pool is weak.
#: Run 38 finished at a 0.39 premium ratio with 32 of 189 inspected candidates
#: flagged as renovation - the search was returning building sites because
#: "paint the trim" and "shelving" are things that happen during building
#: work. These describe the finished room a decorating channel wants, and
#: stock libraries index them heavily.
PREMIUM_QUERIES: tuple[str, ...] = (
    "elegant small living room",
    "bright modern living room interior",
    "cozy scandinavian living room",
    "premium apartment living room",
    "stylish small apartment interior",
    "beautiful home interior daylight",
    "interior design living room",
)

_NOISE = {"the", "a", "an", "of", "and", "with", "for", "in", "on", "to"}


def _normalize(text: str) -> str:
    text = re.sub(r"[^\w\s-]", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _core_subject(query: str) -> str:
    """Strip the room qualifier so a query can be broadened."""

    text = _normalize(query)
    for room in sorted(ROOM_WORDS, key=len, reverse=True):
        if text.endswith(" " + room):
            candidate = text[: -len(room) - 1].strip()
            if len(candidate.split()) >= 2:
                return candidate
        if text.startswith(room + " "):
            candidate = text[len(room) + 1 :].strip()
            if len(candidate.split()) >= 2:
                return candidate
    return text


def _keywords(text: str, limit: int = 4) -> list[str]:
    words = [w for w in _normalize(text).split() if w not in _NOISE and len(w) > 2]
    return words[:limit]


# ---------------------------------------------------------------------------
# Expansion
# ---------------------------------------------------------------------------

def expand_queries(
    tip_queries: Sequence[str],
    narration: str = "",
    category_queries: Sequence[str] = (),
    object_queries: Sequence[str] = (),
    want: int = 8,
    minimum_specific: int = 5,
) -> list[VisualQuery]:
    """Build a ranked ladder of at least ``minimum_specific`` specific queries.

    ``tip_queries`` are the hand-written ones for this idea, ``object_queries``
    come from concrete nouns in this particular sentence, and
    ``category_queries`` are the generic last resort.
    """

    out: list[VisualQuery] = []
    seen: set[str] = set()

    def push(text: str, specificity: str, shot_type: str = "") -> None:
        cleaned = _normalize(text)
        if not cleaned or cleaned in seen or len(cleaned.split()) < 2:
            return
        seen.add(cleaned)
        out.append(VisualQuery(cleaned, specificity, shot_type))

    ordered_tips = [q for q in tip_queries if q]

    # 1. The hand-written queries, alternating the implied framing so an idea
    #    gets a wide establishing shot and a detail rather than four wides.
    for position, query in enumerate(ordered_tips):
        push(query, SPECIFIC, "wide" if position % 2 == 0 else "detail")

    # 2. Framing variants of the strongest one or two subjects.
    for query in ordered_tips[:2]:
        subject = _core_subject(query)
        for modifier in DETAIL_MODIFIERS[:1]:
            push(f"{modifier} {subject}", VARIANT, "detail")
        for modifier in WIDE_MODIFIERS[:1]:
            push(f"{subject} {modifier}", VARIANT, "wide")

    # 3. Objects actually named in this sentence.
    for query in object_queries:
        push(query, SPECIFIC, "detail")

    # 4. Quality-flavoured variants, which also bias results toward the
    #    bright, styled interiors this channel wants.
    if len(out) < want and ordered_tips:
        subject = _core_subject(ordered_tips[0])
        for modifier in QUALITY_MODIFIERS:
            if len(out) >= want:
                break
            push(f"{subject} {modifier}", VARIANT)

    # 5. Broadened forms, used only when the specific phrasings return nothing.
    for query in ordered_tips[:3]:
        subject = _core_subject(query)
        if subject != _normalize(query):
            push(subject, BROAD)
    if narration:
        keywords = _keywords(narration, 3)
        if len(keywords) >= 2:
            push(" ".join(keywords) + " interior", BROAD)

    # 6. Generic category fallback, always last and always flagged.
    for query in category_queries:
        push(query, GENERIC)

    specific_count = sum(1 for q in out if q.specificity in (SPECIFIC, VARIANT))
    if specific_count < minimum_specific and ordered_tips:
        # Guarantee the floor by pairing subjects with remaining modifiers.
        subject = _core_subject(ordered_tips[0])
        for modifier in (*DETAIL_MODIFIERS[1:], *WIDE_MODIFIERS[1:], *QUALITY_MODIFIERS):
            if specific_count >= minimum_specific:
                break
            before = len(out)
            push(f"{subject} {modifier}", VARIANT)
            if len(out) > before:
                specific_count += 1

    return out


def order_by_specificity(queries: Iterable[VisualQuery]) -> list[VisualQuery]:
    """Specific first, generic last - the order searches must be attempted in."""

    return sorted(queries, key=lambda q: SPECIFICITY_ORDER.index(q.specificity))


def generic_ratio(queries: Sequence[VisualQuery]) -> float:
    if not queries:
        return 0.0
    return sum(1 for q in queries if q.is_generic) / len(queries)
