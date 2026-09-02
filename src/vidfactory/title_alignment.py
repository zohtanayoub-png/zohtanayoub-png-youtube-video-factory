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

    # ------------------------------------------------------------------
    # Direct-causation gate.
    #
    # Concept groups alone proved too permissive: the 60-30-10 color rule
    # matched "proportion" and "the eye" and so passed a "make the room look
    # bigger" title, even though nothing about it makes a room look bigger.
    #
    # ``mechanisms`` are the concrete ways an idea can actually cause the
    # promised outcome. When a promise defines any, an idea must match at
    # least one of them - supporting concepts on their own are not enough.
    # ------------------------------------------------------------------
    mechanisms: tuple[tuple[str, ...], ...] = ()
    #: Generic design principles that do not, by themselves, cause the
    #: outcome. Matching one is disqualifying...
    deny_signals: tuple[str, ...] = ()
    #: ...unless the idea explicitly claims the outcome in its own words.
    rescue_signals: tuple[str, ...] = ()

    def describe(self) -> str:
        return f"{self.label} ({self.key})"


#: Phrases that state a perceived-size outcome outright. An idea containing
#: one of these is explaining how it changes how big a room feels, which is
#: what rescues an otherwise generic principle.
SPACE_OUTCOMES: tuple[str, ...] = (
    "look bigger", "looks bigger", "feel bigger", "feels bigger",
    "look larger", "looks larger", "feel larger", "feels larger",
    "appear bigger", "appears bigger", "appear larger", "appears larger",
    "appear taller", "appears taller", "look taller", "looks taller",
    "reads as larger", "reads taller", "read as larger",
    "more spacious", "spacious", "expands", "expand the",
    "recede", "recedes", "receding",
    "shrink", "shrinks", "smaller than it", "feel smaller", "feels smaller",
    "cramped", "boxed in", "keeps going", "room keeps",
    "stretches", "stretch the", "perceived", "visually",
    "sense of space", "feeling of space", "square footage",
)

#: Generic colour-theory and styling principles. Useful advice, but they do
#: not by themselves change how large a room reads.
GENERIC_DESIGN_PRINCIPLES: tuple[str, ...] = (
    "sixty thirty ten", "60 30 10", "sixty percent walls",
    "dominant tone", "supporting tone", "accent color", "accent colour",
    "color rule", "colour rule", "color palette", "colour palette",
    "three colors", "three colours", "undertone", "color scheme",
    "colour scheme", "saturated color", "repeat each accent",
    "pull your palette", "color story",
)

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
        # The concrete ways a room can actually be made to read as larger.
        # Anything that matches none of these is not a space trick, however
        # good the advice is.
        mechanisms=(
            # vertical emphasis
            ("ceiling", "taller", "height", "vertical", "upward", "floor to ceiling",
             "high on the wall", "up to the ceiling", "full height"),
            # continuous sightlines and clear circulation
            ("sightline", "sight line", "continuous", "uninterrupted", "unobstructed",
             "flow", "walkway", "pathway", "circulation", "clear path", "keeps going"),
            # furniture scale and visual weight
            ("fewer, larger", "larger pieces", "oversized", "undersized", "too small",
             "visual weight", "bulky", "heavy", "lighter", "scale"),
            # clutter reduction and negative space
            ("clutter", "declutter", "negative space", "clear surfaces",
             "surfaces stay clear", "empty", "edited", "remove"),
            # visible floor and raised furniture
            ("visible legs", "slim legs", "raised on", "floats", "floating",
             "wall-mount", "wall mounted", "floor continue", "see floor",
             "sits flat on the ground"),
            # mirrors and reflection
            ("mirror", "reflect", "reflection", "glazed", "glass"),
            # light distribution
            ("natural light", "daylight", "sunlight", "bright", "pale",
             "light colour", "light color", "airy", "window"),
            # curtains and window treatment geometry
            ("curtain", "drape", "rod", "panel", "blind"),
            # furniture placement
            ("against the wall", "push", "float the sofa", "placement",
             "arrangement", "layout", "perimeter"),
            # consistent flooring
            ("flooring", "same floor", "one continuous", "floor finish"),
            # avoiding visual fragmentation
            ("chop", "chops", "fragment", "break up", "outline", "hard edge",
             "edges", "same color as the walls", "same colour as the walls",
             "low-contrast", "low contrast"),
            # vertical storage
            ("vertical storage", "up to the ceiling", "storage to the ceiling"),
        ),
        # Supporting evidence, counted only once a mechanism is present.
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
        required_groups=1,
        deny_signals=GENERIC_DESIGN_PRINCIPLES,
        rescue_signals=SPACE_OUTCOMES,
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
        mechanisms=(
            ("material", "stone", "marble", "brass", "solid wood", "leather",
             "wool", "linen", "oak", "walnut"),
            ("finish", "matte", "honed", "gloss", "sheen", "brushed", "polished"),
            ("hardware", "handle", "lever", "knob", "tap", "faucet", "switch plate"),
            ("oversized", "generous", "fuller", "larger", "wider", "scale"),
            ("dimmer", "sconce", "layered", "warm light", "lamp", "picture light"),
            ("moulding", "molding", "panelling", "paneling", "skirting",
             "architectural", "trim", "detail", "junction", "mitred", "edge"),
            ("cable", "cables", "wiring", "conceal", "hidden", "tidy", "plastic"),
            ("upholster", "upholstery", "headboard", "padded", "velvet"),
            ("frame", "framed", "mount", "gallery", "artwork"),
            ("flowers", "branches", "greenery", "plant"),
            ("curtain", "drape", "panel", "hem"),
            ("empty", "clear", "editing", "restraint", "remove"),
        ),
        deny_signals=("acoustic", "water pressure", "scent"),
        rescue_signals=(
            "expensive", "high end", "luxury", "cheap", "designed",
            "considered", "custom", "bespoke", "showroom",
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
        mechanisms=(
            ("warm", "glow", "evening", "low light", "lamp", "candle", "dimmer",
             "kelvin", "2700", "2200"),
            ("soft", "wool", "throw", "cushion", "sheepskin", "linen", "boucle",
             "upholster", "texture", "tactile"),
            ("wood", "timber", "oak", "natural material", "honey", "amber"),
            ("enclos", "nook", "corner", "intimate", "lower", "ceiling",
             "at your back", "window seat"),
            ("acoustic", "sound", "absorb", "echo", "rug", "curtain", "books"),
            ("scent", "senses", "lived in", "personal", "candle"),
        ),
        deny_signals=("resale", "declutter quota", "sixty thirty ten"),
        rescue_signals=("cozy", "cosy", "warm", "inviting", "relax", "comfortable"),
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
        mechanisms=(
            ("light source", "lamp", "bulb", "sconce", "pendant", "dimmer",
             "fixture", "uplight", "led"),
            ("daylight", "window", "sunlight", "natural light", "glass"),
            ("mirror", "reflect", "reflection", "gloss", "sheen"),
            ("pale", "light colour", "light color", "white", "bright"),
            ("kelvin", "warm white", "colour temperature", "color temperature",
             "layer", "layered", "shade", "diffuse"),
            ("curtain", "blind", "clear the sill", "unobstructed"),
        ),
        deny_signals=GENERIC_DESIGN_PRINCIPLES,
        rescue_signals=("bright", "brighter", "light", "dark", "gloomy", "dim"),
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
    #: The direct causal mechanism(s) by which this idea delivers the promise.
    mechanisms: list[str] = field(default_factory=list)
    #: Generic-principle signals that disqualified it, if any.
    denied_by: list[str] = field(default_factory=list)

    def is_aligned(self, threshold: float = DEFAULT_THRESHOLD) -> bool:
        return self.score >= threshold

    @property
    def aligned(self) -> bool:
        return self.is_aligned()

    def explain(self) -> str:
        if self.denied_by:
            return (
                "generic design principle ("
                + ", ".join(self.denied_by[:2])
                + ") with no stated effect on the promised outcome"
            )
        if self.mechanisms:
            reason = "mechanism: " + ", ".join(self.mechanisms[:3])
        elif self.matched_groups:
            reason = (
                "no direct mechanism; only loosely related via "
                + ", ".join(self.matched_groups[:3])
            )
        else:
            reason = "no supporting concept"
        if self.counters:
            reason += "; about " + ", ".join(self.counters[:3]) + " instead"
        return reason


def _hits(text: str, phrases: Sequence[str]) -> list[str]:
    return [p for p in phrases if p in text]


def score_alignment(tip: Tip, promise: Promise) -> AlignmentResult:
    """How strongly one idea supports the promise a title makes (0.0 - 1.0).

    Where a promise defines ``mechanisms``, the idea must contain at least one
    of them: a direct causal route from the idea to the promised outcome.
    Loose topical overlap is deliberately not enough, because that is what let
    the 60-30-10 colour rule into a video about making a room look bigger.
    """

    if promise.key == GENERAL.key or not (promise.concepts or promise.mechanisms):
        return AlignmentResult(tip=tip, score=1.0)

    text = _tip_text(tip)

    # An explicit override on the tip always wins over keyword inference.
    declared = {str(p).lower() for p in tip.get("promises", [])}
    if promise.key in declared:
        return AlignmentResult(tip=tip, score=1.0, mechanisms=["declared"])
    if declared and promise.key not in declared:
        return AlignmentResult(tip=tip, score=0.0, counters=["declared elsewhere"])

    counters = _hits(text, promise.counter_signals)

    # 1. Generic design principles are rejected unless the idea itself
    #    explains that it produces the promised outcome.
    denied = _hits(text, promise.deny_signals)
    if denied:
        rescued = _hits(text, promise.rescue_signals)
        if not rescued:
            return AlignmentResult(
                tip=tip, score=0.0, counters=counters, denied_by=denied
            )

    # 2. Direct-causation gate.
    mechanisms: list[str] = []
    if promise.mechanisms:
        for group in promise.mechanisms:
            hit = next((word for word in group if word in text), None)
            if hit:
                mechanisms.append(hit)
        if not mechanisms:
            return AlignmentResult(tip=tip, score=0.0, counters=counters)

    # 3. Supporting concepts refine the score once causation is established.
    matched: list[str] = []
    for group in promise.concepts:
        hit = next((word for word in group if word in text), None)
        if hit:
            matched.append(hit)

    if len(matched) < max(1, promise.required_groups):
        return AlignmentResult(
            tip=tip, score=0.0, matched_groups=matched,
            counters=counters, mechanisms=mechanisms,
        )

    if promise.mechanisms:
        # Causation established: score on how many independent mechanisms and
        # supporting concepts back it up.
        strength = min(1.0, 0.42 + 0.16 * len(mechanisms) + 0.06 * len(matched))
    else:
        # Promises without a mechanism list keep the older concept-count rule.
        strength = min(1.0, 0.18 + 0.26 * len(matched))

    score = max(0.0, strength - 0.3 * len(counters))
    return AlignmentResult(
        tip=tip,
        score=round(score, 3),
        matched_groups=matched,
        counters=counters,
        mechanisms=mechanisms,
    )


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
