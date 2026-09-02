"""Title-promise validation.

A title is a promise. "25 Small Living Room Ideas That Make Any Space Look
Bigger" promises that every idea makes a room look bigger - not that every
idea is merely good interior design advice.

Before the script is written, each candidate idea is scored against the
promise the title makes. Ideas that do not directly support it are rejected
and replaced. Matching the coffee table height to the sofa seat is sound
advice and has nothing to do with perceived space, so it does not belong in a
"look bigger" video.

The scoring is deliberately transparent - keyword concepts and explicit
counter-signals - so a rejection can always be explained in the log and in the
editorial quality report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .logging_utils import get_logger

log = get_logger("ALIGN")

Tip = dict[str, Any]


@dataclass(frozen=True)
class Promise:
    """What a title commits every idea in the video to deliver."""

    key: str
    label: str
    #: Phrases in a title that mean the video is making this promise.
    title_signals: tuple[str, ...]
    #: Concept groups. An idea must touch at least ``required_groups`` of them.
    concepts: tuple[tuple[str, ...], ...]
    #: Signals that an idea is about something else entirely.
    counter_signals: tuple[str, ...] = ()
    required_groups: int = 1

    def describe(self) -> str:
        return f"{self.label} ({self.key})"


#: Ordered by specificity - the first title signal that matches wins.
PROMISES: tuple[Promise, ...] = (
    Promise(
        key="bigger",
        label="make the space look or feel bigger",
        title_signals=(
            "look bigger", "feel bigger", "look larger", "feel larger",
            "appear bigger", "space look bigger", "maximize space",
            "look more spacious", "feel more spacious", "make any space",
        ),
        concepts=(
            ("ceiling", "tall", "taller", "height", "vertical", "upward", "high"),
            ("mirror", "reflect", "reflection", "glass", "transparent"),
            ("light", "daylight", "bright", "sunlight", "window", "pale", "airy"),
            ("legs", "floor", "visible floor", "float", "raised", "wall mount"),
            ("scale", "oversized", "larger", "fewer", "bigger", "proportion"),
            ("clutter", "declutter", "surfaces", "empty", "negative space", "edited"),
            ("sightline", "continuous", "flow", "uninterrupted", "open", "path"),
            ("contrast", "outline", "edges", "recede", "same color", "low-contrast"),
            ("storage", "vertical storage", "hidden", "conceal"),
            ("visual weight", "heavy", "heavier", "lighter", "weight", "bulky",
             "reads as", "the eye", "your brain", "perceived"),
        ),
        required_groups=2,
        counter_signals=(
            "conversation", "comfort", "cozy", "scent", "sound", "acoustic",
            "seasonal", "maintenance", "regrout", "towel", "water pressure",
            "shower head", "reach", "arm's reach", "within reach",
        ),
    ),
    Promise(
        key="expensive",
        label="make the home look more expensive",
        title_signals=(
            "look more expensive", "look expensive", "high end", "luxury",
            "look cheap", "make a space look cheap", "designer",
        ),
        concepts=(
            ("material", "stone", "marble", "brass", "solid wood", "leather", "wool", "linen"),
            ("finish", "matte", "honed", "gloss", "sheen", "hardware", "handle", "trim"),
            ("scale", "oversized", "generous", "larger", "full", "fuller"),
            ("light", "lighting", "lamp", "sconce", "dimmer", "warm", "layered"),
            ("detail", "edge", "junction", "moulding", "panelling", "architectural"),
            ("cable", "clutter", "plastic", "tidy", "conceal", "hidden"),
            ("curtain", "drapery", "fabric", "upholster", "upholstery"),
            ("art", "frame", "mount", "gallery"),
            ("flowers", "greenery", "plant", "branches"),
        ),
        counter_signals=("acoustic", "sound", "scent", "seasonal", "quota"),
    ),
    Promise(
        key="cozy",
        label="make the home feel warmer and cozier",
        title_signals=("cozy", "cosy", "warmer home", "feel warmer", "inviting"),
        concepts=(
            ("warm", "warmth", "glow", "evening", "low light", "lamp", "candle", "dimmer"),
            ("soft", "texture", "wool", "throw", "cushion", "sheepskin", "linen", "upholster"),
            ("wood", "natural", "material", "tactile"),
            ("enclos", "nook", "corner", "intimate", "ceiling", "lower"),
            ("acoustic", "sound", "absorb", "rug", "curtain", "books"),
            ("scent", "senses", "lived in", "personal"),
        ),
        counter_signals=("declutter quota", "resale"),
    ),
    Promise(
        key="storage",
        label="add storage or reduce clutter",
        title_signals=("storage", "organiz", "organis", "declutter", "clutter"),
        concepts=(
            ("storage", "store", "stored", "storing"),
            ("shelf", "shelving", "cabinet", "cupboard", "drawer", "wardrobe", "closet"),
            ("basket", "box", "container", "bin", "label"),
            ("hidden", "conceal", "under bed", "ottoman", "bench", "hook", "rail"),
            ("vertical", "ceiling", "above", "door", "wall"),
            ("clutter", "declutter", "tidy", "system", "sort", "outbox"),
        ),
        counter_signals=("paint color", "curtain length", "scent"),
    ),
    Promise(
        key="mistakes",
        label="identify a mistake worth fixing",
        title_signals=("mistake", "avoid", "never break", "designers never", "wrong"),
        # Almost any idea can be framed as a mistake, so the bar is a concrete,
        # correctable, physical decision rather than a vague principle.
        concepts=(
            ("too small", "too high", "too low", "too far", "wrong", "avoid", "mistake"),
            ("instead", "rather than", "should", "never", "stop"),
            ("size", "scale", "height", "proportion", "placement", "position"),
            ("light", "color", "rug", "curtain", "art", "furniture", "storage"),
        ),
    ),
    Promise(
        key="budget",
        label="deliver the result on a small budget",
        title_signals=("budget", "affordable", "cheap", "under", "for less", "on a small budget"),
        concepts=(
            ("budget", "cost", "cheap", "affordable", "inexpensive", "free", "spend"),
            ("secondhand", "vintage", "diy", "paint", "swap", "replace", "upgrade"),
            ("dollars", "price", "value", "worth"),
            ("already own", "shop your own", "rearrange", "move", "clean", "repair"),
        ),
        counter_signals=("bespoke", "custom joinery"),
    ),
    Promise(
        key="timeless",
        label="stay in style for years",
        title_signals=("timeless", "never go out of style", "classic", "always"),
        concepts=(
            ("timeless", "classic", "age", "ages", "aging", "decade", "years", "lasting"),
            ("neutral", "plain", "simple", "restraint", "understated"),
            ("material", "solid wood", "stone", "leather", "wool", "brass", "patina"),
            ("trend", "dated", "era", "cycle", "fashion"),
            ("proportion", "architecture", "light", "flow"),
        ),
        counter_signals=("trend of the year", "seasonal"),
    ),
    Promise(
        key="renter",
        label="work in a rental without permanent changes",
        title_signals=("rental", "renter", "without drilling", "landlord", "temporary"),
        concepts=(
            ("rent", "rental", "renter", "landlord", "deposit", "move"),
            ("removable", "temporary", "reversible", "no drill", "tension", "adhesive", "peel"),
            ("freestanding", "portable", "leaning", "swap", "store the original"),
        ),
        counter_signals=("built in", "knock through", "replace the floor"),
    ),
    Promise(
        key="brighter",
        label="bring more light into the room",
        title_signals=("brighter", "more light", "lighting", "dark room", "light up"),
        concepts=(
            ("light", "lighting", "lamp", "bulb", "sconce", "pendant", "dimmer"),
            ("daylight", "window", "sunlight", "natural light", "curtain"),
            ("mirror", "reflect", "pale", "bright", "white", "gloss"),
            ("layer", "warm", "kelvin", "shade", "glow"),
        ),
    ),
)

#: When a title makes no specific promise, every idea in the category is fair
#: game and the stage passes everything through.
GENERAL = Promise(
    key="general",
    label="useful ideas for this room or topic",
    title_signals=(),
    concepts=(),
    required_groups=0,
)


def detect_promise(title: str, angle: str = "") -> Promise:
    """Work out what a title actually commits the video to."""

    text = f" {re.sub(r'[^a-z ]+', ' ', str(title or '').lower())} "
    for promise in PROMISES:
        for signal in promise.title_signals:
            if signal in text:
                return promise
    # The topic engine's angle is a weaker second opinion.
    angle_map = {
        "space": "bigger",
        "expensive": "expensive",
        "cozy": "cozy",
        "storage": "storage",
        "mistakes": "mistakes",
        "budget": "budget",
        "timeless": "timeless",
    }
    key = angle_map.get(str(angle or "").lower())
    if key:
        for promise in PROMISES:
            if promise.key == key:
                return promise
    return GENERAL


def _tip_text(tip: Tip) -> str:
    """All the text that describes an idea, including its visual queries.

    The queries are hand-written descriptions of what the idea looks like
    ("airy small living space"), so they carry real signal about what the idea
    is for and are included deliberately.
    """

    parts = [
        str(tip.get("title", "")),
        str(tip.get("why", "")),
        str(tip.get("how", "")),
        str(tip.get("mistake", "")),
        " ".join(str(t) for t in tip.get("tags", [])),
        " ".join(str(q) for q in tip.get("queries", [])),
    ]
    return " ".join(parts).lower()


#: An idea must clear this to be considered "supports the title promise".
DEFAULT_THRESHOLD = 0.5


@dataclass
class AlignmentResult:
    tip: Tip
    score: float
    matched_groups: list[str] = field(default_factory=list)
    counters: list[str] = field(default_factory=list)

    def is_aligned(self, threshold: float = DEFAULT_THRESHOLD) -> bool:
        return self.score >= threshold

    @property
    def aligned(self) -> bool:
        return self.is_aligned()

    def explain(self) -> str:
        if self.matched_groups:
            reason = "matched " + ", ".join(self.matched_groups[:4])
        else:
            reason = "no supporting concept"
        if self.counters:
            reason += "; about " + ", ".join(self.counters[:3]) + " instead"
        return reason


def score_alignment(tip: Tip, promise: Promise) -> AlignmentResult:
    """How strongly one idea supports the promise a title makes (0.0 - 1.0)."""

    if promise.key == GENERAL.key or not promise.concepts:
        return AlignmentResult(tip=tip, score=1.0)

    text = _tip_text(tip)

    # An explicit override on the tip always wins over keyword inference.
    declared = {str(p).lower() for p in tip.get("promises", [])}
    if promise.key in declared:
        return AlignmentResult(tip=tip, score=1.0, matched_groups=["declared"])
    if declared and promise.key not in declared:
        return AlignmentResult(tip=tip, score=0.0, counters=["declared elsewhere"])

    matched: list[str] = []
    for group in promise.concepts:
        hit = next((word for word in group if word in text), None)
        if hit:
            matched.append(hit)

    counters = [word for word in promise.counter_signals if word in text]

    if len(matched) < max(1, promise.required_groups):
        return AlignmentResult(tip=tip, score=0.0, matched_groups=matched, counters=counters)

    # A single incidental keyword is not evidence that an idea serves the
    # promise, so one matched group deliberately lands below the threshold.
    # Two independent groups clear it; three make it a strong fit.
    strength = min(1.0, 0.18 + 0.26 * len(matched))
    penalty = 0.3 * len(counters)
    score = max(0.0, strength - penalty)
    return AlignmentResult(tip=tip, score=round(score, 3), matched_groups=matched, counters=counters)


def filter_aligned(
    tips: Sequence[Tip],
    promise: Promise,
    threshold: float = DEFAULT_THRESHOLD,
    minimum: int = 3,
) -> tuple[list[Tip], list[AlignmentResult]]:
    """Keep only ideas that support the promise; report the ones dropped.

    If filtering leaves too little material to build a video, the threshold is
    relaxed once - a short honest video beats a crash - and the relaxation is
    logged rather than hidden.
    """

    scored = [score_alignment(tip, promise) for tip in tips]
    kept = [r for r in scored if r.score >= threshold]
    rejected = [r for r in scored if r.score < threshold]

    if len(kept) < minimum:
        relaxed = sorted(scored, key=lambda r: r.score, reverse=True)[:minimum]
        if relaxed and relaxed[0].score > 0:
            log.warning(
                "Only %d of %d ideas clearly support '%s'; relaxing the "
                "threshold to keep the video viable",
                len(kept),
                len(scored),
                promise.label,
            )
            kept = relaxed
            rejected = [r for r in scored if r not in kept]

    kept.sort(key=lambda r: r.score, reverse=True)
    return [r.tip for r in kept], rejected


def alignment_ratio(
    tips: Sequence[Tip], promise: Promise, threshold: float = DEFAULT_THRESHOLD
) -> float:
    """Share of the chosen ideas that actually support the title."""

    if not tips:
        return 0.0
    hits = sum(1 for tip in tips if score_alignment(tip, promise).score >= threshold)
    return round(hits / len(tips), 3)
