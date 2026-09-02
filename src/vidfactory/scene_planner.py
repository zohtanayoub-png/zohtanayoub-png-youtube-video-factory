"""Scene planning: turn a narration script into visually-searchable scenes.

Stock footage is never searched with the video title. Instead the script is
broken into short narration scenes, and every scene carries its own primary
and alternative visual queries derived from what that specific sentence is
about. That is what makes the footage follow the narration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .logging_utils import get_logger
from .script_generator import Script, ScriptSection

log = get_logger("SCENES")

#: Roughly how many words of American English narration fit into one second.
WORDS_PER_SECOND = 2.5

_ABBREV = ("mr", "mrs", "ms", "dr", "st", "vs", "etc", "e.g", "i.e", "approx")

# Concrete decor objects worth searching for when they appear in narration.
VISUAL_TERMS: dict[str, str] = {
    "curtain": "curtains interior window",
    "drape": "curtains interior window",
    "rug": "area rug living room floor",
    "carpet": "area rug living room floor",
    "sofa": "modern sofa living room",
    "couch": "modern sofa living room",
    "armchair": "armchair interior corner",
    "chair": "interior chair design",
    "coffee table": "coffee table styling living room",
    "console": "console table interior styling",
    "nightstand": "nightstand bedside table bedroom",
    "bed": "made bed bedroom interior",
    "headboard": "upholstered headboard bedroom",
    "bedding": "layered bedding bedroom",
    "pillow": "cushions styled sofa",
    "cushion": "cushions styled sofa",
    "throw": "throw blanket sofa cozy",
    "lamp": "table lamp warm light interior",
    "sconce": "wall sconce interior lighting",
    "pendant": "pendant light interior",
    "chandelier": "chandelier interior lighting",
    "bulb": "warm light bulb interior",
    "dimmer": "dimmed warm interior lighting",
    "candle": "candles warm interior evening",
    "mirror": "large mirror interior wall",
    "plant": "indoor plant interior decor",
    "tree": "large indoor plant interior",
    "flower": "fresh flowers vase interior",
    "branch": "branches in vase interior",
    "shelf": "styled shelf interior",
    "shelving": "shelving unit interior wall",
    "bookcase": "bookshelf full of books interior",
    "cabinet": "cabinet interior storage",
    "cabinetry": "modern cabinetry interior",
    "drawer": "organized drawer interior",
    "wardrobe": "wardrobe closet interior",
    "closet": "organized closet interior",
    "counter": "kitchen countertop clean",
    "countertop": "kitchen countertop clean",
    "backsplash": "kitchen backsplash tile",
    "island": "kitchen island interior",
    "sink": "sink interior detail",
    "tap": "tap faucet detail interior",
    "faucet": "tap faucet detail interior",
    "shower": "modern shower bathroom",
    "towel": "folded towels bathroom",
    "tile": "tile detail interior",
    "grout": "clean tile detail bathroom",
    "paint": "painting a wall interior",
    "wall": "interior wall detail",
    "ceiling": "interior ceiling design",
    "trim": "interior trim molding detail",
    "molding": "wall molding detail interior",
    "panel": "wall paneling interior",
    "door": "interior door detail",
    "handle": "door handle hardware detail",
    "hardware": "cabinet hardware detail",
    "window": "bright window interior daylight",
    "daylight": "sunlight through window interior",
    "art": "framed art on wall interior",
    "frame": "framed artwork interior wall",
    "gallery wall": "gallery wall interior",
    "vase": "ceramic vase interior styling",
    "ceramic": "ceramic objects interior styling",
    "basket": "woven basket interior storage",
    "bench": "bench interior seating",
    "ottoman": "storage ottoman living room",
    "stool": "wooden stool interior",
    "desk": "home office desk interior",
    "dining table": "dining table interior",
    "table": "wooden table interior",
    "wood": "wooden texture interior detail",
    "linen": "linen fabric texture interior",
    "wool": "wool texture blanket interior",
    "leather": "leather furniture detail interior",
    "stone": "natural stone surface interior",
    "marble": "marble surface detail interior",
    "brass": "brass detail interior",
    "plaster": "textured plaster wall interior",
    "storage": "home storage organization",
    "clutter": "tidy organized interior surfaces",
    "entry": "entryway interior home",
    "hallway": "hallway interior home",
    "balcony": "apartment balcony plants",
    "fireplace": "fireplace living room interior",
    "television": "television living room interior",
    "cable": "tidy cables interior detail",
}

#: Fallback queries by room / style category, used when a sentence has no
#: strong concrete subject of its own.
CATEGORY_QUERIES: dict[str, list[str]] = {
    "living rooms": ["modern living room interior", "cozy living room design", "bright living room home"],
    "bedrooms": ["modern bedroom interior", "cozy bedroom design", "calm bedroom home"],
    "kitchens": ["modern kitchen interior", "bright kitchen design", "clean kitchen home"],
    "bathrooms": ["modern bathroom interior", "bright bathroom design", "spa bathroom home"],
    "small spaces": ["small apartment interior", "compact living space", "studio apartment design"],
    "home organization": ["organized home interior", "tidy home storage", "home organization shelves"],
    "lighting": ["warm interior lighting", "cozy lamp light home", "evening interior lighting"],
    "colors": ["interior color palette", "painted interior wall", "neutral interior design"],
    "furniture placement": ["living room furniture layout", "furniture arrangement interior", "spacious interior room"],
    "storage": ["home storage solutions", "built in storage interior", "organized shelving home"],
    "expensive look": ["luxury interior detail", "elegant home interior", "high end interior design"],
    "interior design mistakes": ["interior design detail", "living room interior", "home decor interior"],
    "budget decorating": ["affordable home decor", "simple interior decor", "cozy budget interior"],
    "renter-friendly decorating": ["rental apartment interior", "small apartment decor", "modern rented apartment"],
    "cozy homes": ["cozy home interior evening", "warm cozy living room", "hygge home interior"],
    "minimalist design": ["minimalist interior design", "minimal living room", "clean minimal home"],
    "scandinavian design": ["scandinavian interior design", "nordic living room", "bright scandinavian home"],
    "modern homes": ["modern interior design", "contemporary living room", "modern home interior"],
    "luxury interiors": ["luxury interior design", "elegant living room", "luxury home interior"],
    "apartment decorating": ["apartment interior design", "modern apartment living room", "city apartment interior"],
    "farmhouse design": ["farmhouse interior design", "rustic kitchen interior", "country home interior"],
    "mediterranean design": ["mediterranean interior design", "terracotta interior", "warm textured interior"],
    "seasonal decorating": ["seasonal home decor", "cozy autumn interior", "decorated home interior"],
    "timeless interiors": ["classic interior design", "timeless living room", "elegant neutral interior"],
    "diy decor": ["diy home project interior", "home improvement interior", "handmade home decor"],
    "design trends": ["modern interior trend", "contemporary interior design", "stylish home interior"],
}

_GENERIC_QUERIES = [
    "modern home interior design",
    "beautiful interior living space",
    "cozy home interior",
    "bright interior design home",
]


@dataclass
class Scene:
    """One narration unit and the visuals that should accompany it."""

    scene_id: str
    narration: str
    estimated_duration: float
    primary_visual_query: str
    alternative_visual_queries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    visual_category: str = ""
    section_kind: str = "item"
    section_index: int = 0

    @property
    def queries(self) -> list[str]:
        return [self.primary_visual_query, *self.alternative_visual_queries]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "narration": self.narration,
            "estimated_duration": round(self.estimated_duration, 2),
            "primary_visual_query": self.primary_visual_query,
            "alternative_visual_queries": list(self.alternative_visual_queries),
            "keywords": list(self.keywords),
            "visual_category": self.visual_category,
            "section_kind": self.section_kind,
            "section_index": self.section_index,
        }


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    """Split narration into sentences without breaking on abbreviations."""

    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    sentences: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lowered = part.rstrip(".").lower().split()[-1] if part.rstrip(".") else ""
        if sentences and lowered in _ABBREV:
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)
    return sentences


def group_sentences(sentences: Sequence[str], max_words: int = 34) -> list[str]:
    """Group short sentences so every scene carries a few seconds of narration."""

    groups: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        words = len(sentence.split())
        if current and current_words + words > max_words:
            groups.append(" ".join(current))
            current, current_words = [sentence], words
        else:
            current.append(sentence)
            current_words += words
    if current:
        groups.append(" ".join(current))
    return groups


def estimate_duration(text: str, words_per_second: float = WORDS_PER_SECOND) -> float:
    words = len(text.split())
    return max(1.5, words / max(words_per_second, 0.5))


# ---------------------------------------------------------------------------
# Query derivation
# ---------------------------------------------------------------------------

def _matched_terms(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    hits: list[tuple[int, str]] = []
    for term, query in VISUAL_TERMS.items():
        position = lowered.find(f" {term}")
        if position >= 0:
            # Longer terms are more specific, so they win ties.
            hits.append((position - len(term) * 4, query))
    hits.sort()
    ordered: list[str] = []
    for _, query in hits:
        if query not in ordered:
            ordered.append(query)
    return ordered


def derive_queries(
    narration: str,
    category: str,
    tip_queries: Sequence[str] = (),
    limit: int = 5,
) -> list[str]:
    """Build a ranked query list for one scene, most specific first."""

    queries: list[str] = []

    def push(value: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(value)).strip().lower()
        if cleaned and cleaned not in queries:
            queries.append(cleaned)

    # 1. Queries hand-written for this specific tip are the most reliable.
    for query in tip_queries:
        push(query)
    # 2. Concrete objects mentioned in this exact sentence.
    for query in _matched_terms(narration):
        push(query)
    # 3. Category-level fallbacks.
    for query in CATEGORY_QUERIES.get(category, []):
        push(query)
    # 4. Absolute fallbacks so a scene is never left without a query.
    for query in _GENERIC_QUERIES:
        push(query)

    return queries[:limit]


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z]{4,}", text.lower())
    stop = {
        "that", "this", "with", "from", "your", "they", "them", "will", "have",
        "into", "than", "when", "what", "which", "because", "there", "their",
        "about", "would", "could", "should", "just", "like", "make", "makes",
        "does", "very", "more", "most", "some", "much", "even", "only", "also",
    }
    unique = [w for w in dict.fromkeys(words) if w not in stop]
    return unique[:8]


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class ScenePlanner:
    """Breaks a :class:`Script` into :class:`Scene` objects."""

    def __init__(self, max_words_per_scene: int = 34, words_per_second: float = WORDS_PER_SECOND) -> None:
        self.max_words_per_scene = int(max_words_per_scene)
        self.words_per_second = float(words_per_second)

    def plan(self, script: Script) -> list[Scene]:
        category = script.topic.category
        scenes: list[Scene] = []

        for section in script.sections:
            tip_queries = list((section.tip or {}).get("queries", []))
            groups = group_sentences(
                split_sentences(section.text), max_words=self.max_words_per_scene
            )
            for order, narration in enumerate(groups):
                queries = derive_queries(
                    narration,
                    category,
                    # The tip's own queries lead the first scene of an item;
                    # later scenes lean on what their own sentence mentions.
                    tip_queries if order == 0 else tip_queries[1:],
                )
                scene_id = f"{section.kind}-{section.index:03d}-{order:02d}"
                scenes.append(
                    Scene(
                        scene_id=scene_id,
                        narration=narration,
                        estimated_duration=estimate_duration(narration, self.words_per_second),
                        primary_visual_query=queries[0],
                        alternative_visual_queries=queries[1:],
                        keywords=_keywords(narration),
                        visual_category=category,
                        section_kind=section.kind,
                        section_index=section.index,
                    )
                )

        total = sum(scene.estimated_duration for scene in scenes)
        log.info(
            "%d scenes created (estimated %s of narration)", len(scenes), _fmt(total)
        )
        return scenes


def _fmt(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes:d}:{secs:02d}"


def plan_scenes(script: Script, max_words_per_scene: int = 34) -> list[Scene]:
    return ScenePlanner(max_words_per_scene=max_words_per_scene).plan(script)
