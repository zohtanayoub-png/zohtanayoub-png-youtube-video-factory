"""Whether a causal sentence actually explains *this* section.

:mod:`vidfactory.concepts` asks whether an explanation is about the same
physical thing as its heading, and catches a curtain sentence in an art
section. Run 25 shipped two failures it cannot see, because neither is about
the wrong object - both are about the wrong *idea*.

**A principle is not an object.** Idea 15 read:

    Balance visual weight across the room
    ... Oversized furniture eats visible floor area and narrows the walking
    paths, so the room feels tighter.

``cross_concept_contamination_count`` came back 0, correctly by its own
rules: "balance visual weight" names no physical thing at all, so there was
no subject for the sentence to disagree with. But balance is about where
visual mass sits, and that sentence is about how much floor a sofa covers.
They are different pieces of advice, and the second is not a reason for the
first. :func:`find_principle_contamination` gives abstract headings a subject
of their own so the comparison can happen.

**An optional example is not the principle.** Idea 8 read:

    Leave the corners of the room resolved
    ... a plant, a floor lamp, a mirror or a low chair ...
    A reflection adds depth, so the room reads larger than it measures.

Every word of that is true, and it justifies exactly one of the four options.
A reader who puts a plant in the corner has been given no reason at all.
:func:`find_optional_example_leakage` catches a general recommendation resting
on one of its own alternatives, and the fix is either an explanation that
covers the principle or an honest condition: *if you use a mirror, ...*.

Both checks are deliberately conservative. They fire only when the sentence
carries a causal connective, when it uses a competing vocabulary at least
twice, and when it uses none of the section's own - because the cost of a
false positive here is a rewritten paragraph that was already correct.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .entities import entities_in, required_entity
from .logging_utils import get_logger

log = get_logger("PRINCIPLE")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

#: Enough of a competing vocabulary to mean the sentence is really about it.
#: One word is a coincidence - "floor" appears in advice about everything.
FOREIGN_HITS_REQUIRED = 2


@dataclass(frozen=True)
class Principle:
    """One idea a section can be about, as opposed to one thing.

    ``triggers`` are matched against the heading, which is where the section
    declares what it is teaching. ``vocabulary`` is what an explanation of
    that idea unavoidably reaches for: you cannot explain balance without
    saying something about weight, sides or distribution.
    """

    name: str
    triggers: tuple[str, ...]
    vocabulary: tuple[str, ...]


PRINCIPLES: tuple[Principle, ...] = (
    Principle(
        name="visual_weight_balance",
        triggers=(
            "balance", "balanced", "balancing", "visual weight", "equilibrium",
            "symmetry", "symmetrical", "evenly",
        ),
        vocabulary=(
            "visual weight", "visual mass", "weight", "weighted", "heavy",
            "heavier", "heaviest", "dark", "darker", "bulk", "one side",
            "both sides", "each side", "either side", "opposite side",
            "distribute", "distributed", "distribution", "spread", "evenly",
            "even", "equilibrium", "anchor", "anchors", "counterweight",
            "balance", "balanced", "lopsided", "overloaded", "top heavy",
            "settles", "settle",
        ),
    ),
    Principle(
        name="furniture_footprint",
        triggers=(
            "oversized furniture", "footprint", "furniture scale",
            "bulky", "too big for", "furniture size", "scale the furniture",
        ),
        vocabulary=(
            "footprint", "walking path", "walking paths", "walkway",
            "walkways", "clearance", "oversized", "bulky", "eats", "eat",
            "takes up", "take up", "square footage", "circulation",
            "squeeze", "squeezed", "narrows", "narrow",
        ),
    ),
    Principle(
        name="corner_treatment",
        triggers=("corner", "corners"),
        vocabulary=(
            "corner", "corners", "dead space", "dead zone", "unused",
            "unresolved", "resolved", "finished", "abandoned", "forgotten",
        ),
    ),
    Principle(
        name="clutter_editing",
        triggers=(
            "clutter", "declutter", "edit down", "what is on show",
            "on show", "surfaces clear", "put away", "fewer",
        ),
        vocabulary=(
            "clutter", "cluttered", "surface", "surfaces", "objects", "items",
            "fewer", "count", "visual noise", "noise", "busy", "busier",
            "tidy", "out of sight", "on show", "scattered",
        ),
    ),
    Principle(
        name="sightline_depth",
        triggers=(
            "sightline", "sightlines", "line of sight", "see through",
            "depth", "across the room", "through the room",
        ),
        vocabulary=(
            "sightline", "sightlines", "line of sight", "see through",
            "sees through", "depth", "distance", "far wall", "back wall",
            "uninterrupted", "travels", "carries", "further", "farther",
            "beyond",
        ),
    ),
    Principle(
        name="vertical_emphasis",
        triggers=(
            "eye level", "height", "high", "tall", "vertical", "ceiling",
            "hang", "hanging", "up the wall",
        ),
        vocabulary=(
            "vertical", "vertically", "height", "tall", "taller", "ceiling",
            "ceilings", "upward", "upwards", "up the wall", "eye level",
            "higher", "lift", "lifts", "raised", "top", "overhead",
        ),
    ),
    Principle(
        name="light_reflection",
        triggers=(
            "light", "lighting", "daylight", "reflect", "reflection",
            "bright", "brighter", "dark corners", "lamp", "lamps",
        ),
        vocabulary=(
            "light", "lights", "lit", "daylight", "sunlight", "reflect",
            "reflects", "reflection", "bounce", "bounces", "bright",
            "brighter", "brightness", "shadow", "shadows", "glow", "lumens",
            "pool of light", "dim", "dimmer",
        ),
    ),
    Principle(
        name="color_continuity",
        triggers=(
            "same color", "same colour", "one color", "one colour", "tonal",
            "monochrome", "contrast", "palette", "match the wall",
        ),
        vocabulary=(
            "color", "colour", "colors", "colours", "tone", "tones", "tonal",
            "contrast", "contrasts", "seam", "seams", "boundary", "boundaries",
            "edge", "edges", "blend", "blends", "continuous", "continuity",
            "break", "breaks", "line where", "palette", "shade", "shades",
        ),
    ),
    Principle(
        name="floor_visibility",
        triggers=(
            "floor", "legs", "exposed legs", "raised", "float", "floating",
            "off the floor",
        ),
        vocabulary=(
            "floor", "floors", "floor area", "flooring", "underneath",
            "under it", "legs", "visible floor", "bare floor", "ground",
            "continuous floor", "uninterrupted floor",
        ),
    ),
)

BY_NAME: dict[str, Principle] = {p.name: p for p in PRINCIPLES}

#: Principles close enough that borrowing each other's language is fair.
#: How much floor a sofa covers and how much floor you can see are two
#: descriptions of one fact, and daylight advice is lighting advice.
COMPATIBLE: dict[str, frozenset[str]] = {
    "furniture_footprint": frozenset({"floor_visibility", "sightline_depth"}),
    "floor_visibility": frozenset({"furniture_footprint", "sightline_depth"}),
    "sightline_depth": frozenset({"floor_visibility", "furniture_footprint"}),
    "light_reflection": frozenset({"color_continuity"}),
    "color_continuity": frozenset({"light_reflection"}),
    "vertical_emphasis": frozenset({"sightline_depth"}),
    "corner_treatment": frozenset({"light_reflection", "floor_visibility"}),
}

#: A sentence that admits it only covers one option is not leakage.
CONDITIONAL_MARKERS: tuple[str, ...] = (
    "if you", "if a ", "if the", "if that", "when you", "where you",
    "should you", "in that case", "with a mirror", "whichever", "either way",
    "for the mirror", "in the mirror's case",
)

#: Same idea in Spanish, so a Spanish script is held to the same rule.
CONDITIONAL_MARKERS_ES: tuple[str, ...] = (
    "si usas", "si pones", "si eliges", "si el ", "si la ", "cuando pongas",
    "en ese caso", "en el caso del espejo",
)


def _normalise(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9áéíóúüñ ]+', ' ', str(text or '').lower())} "


def _vocabulary_hits(words: Sequence[str], haystack: str) -> int:
    return sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", haystack))


def primary_principle(heading: str, tip: Mapping[str, Any] | None = None) -> Principle | None:
    """The idea this section teaches, from its heading.

    The heading only. An idea's body reaches for whatever it needs, and
    judging the section's subject by its body is what makes every section
    about everything - the same reason :func:`concepts.subject_concepts`
    stays out of the body.
    """

    parts = [str(heading or "")]
    if tip:
        parts.append(str(tip.get("title", "")))
    haystack = _normalise(" ".join(parts))
    if not haystack.strip():
        return None

    best: tuple[int, int, Principle] | None = None
    for principle in PRINCIPLES:
        hits = _vocabulary_hits(principle.triggers, haystack)
        if not hits:
            continue
        first = min(
            (m.start() for word in principle.triggers
             if (m := re.search(rf"\b{re.escape(word)}\b", haystack))),
            default=len(haystack),
        )
        if best is None or (first, -hits) < (best[0], best[1]):
            best = (first, -hits, principle)
    return best[2] if best else None


def is_compatible(subject: str, other: str) -> bool:
    if not subject or not other or subject == other:
        return True
    return other in COMPATIBLE.get(subject, frozenset())


@dataclass
class PrincipleContamination:
    """A causal sentence that explains a different idea than the heading's."""

    index: int = 0
    heading: str = ""
    principle: str = ""
    intruder: str = ""
    sentence: str = ""

    def explain(self) -> str:
        return (
            f"the section teaches {self.principle.replace('_', ' ')} "
            f"but this sentence explains {self.intruder.replace('_', ' ')}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "heading": self.heading,
            "principle": self.principle,
            "intruder": self.intruder,
            "sentence": self.sentence[:200],
            "why": self.explain(),
        }


@dataclass
class OptionalExampleLeakage:
    """A general recommendation justified through one of its own options."""

    index: int = 0
    heading: str = ""
    options: list[str] = field(default_factory=list)
    used: str = ""
    sentence: str = ""

    def explain(self) -> str:
        return (
            f"the section offers {', '.join(sorted(self.options))} but the "
            f"explanation only holds for {self.used}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "heading": self.heading,
            "options": sorted(self.options),
            "used": self.used,
            "sentence": self.sentence[:200],
            "why": self.explain(),
        }


def _causal_sentences(text: str, connectives: Sequence[str]) -> list[str]:
    """Sentences that claim a consequence, which are the ones under test."""

    out: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(str(text or "")):
        stripped = sentence.strip()
        if not stripped:
            continue
        lowered = f" {stripped.lower()} "
        if any(c.strip() and c in lowered for c in connectives):
            out.append(stripped)
    return out


def find_principle_contamination(
    heading: str,
    text: str,
    tip: Mapping[str, Any] | None = None,
    connectives: Sequence[str] = (),
) -> list[PrincipleContamination]:
    """Causal sentences that explain an idea the section is not teaching."""

    principle = primary_principle(heading, tip)
    if principle is None:
        return []

    found: list[PrincipleContamination] = []
    for sentence in _causal_sentences(text, connectives):
        haystack = _normalise(sentence)
        if _vocabulary_hits(principle.vocabulary, haystack):
            continue                    # it does speak the section's language
        intruder: tuple[int, Principle] | None = None
        for other in PRINCIPLES:
            if other.name == principle.name or is_compatible(principle.name, other.name):
                continue
            hits = _vocabulary_hits(other.vocabulary, haystack)
            if hits >= FOREIGN_HITS_REQUIRED and (intruder is None or hits > intruder[0]):
                intruder = (hits, other)
        if intruder is None:
            continue
        found.append(
            PrincipleContamination(
                heading=str(heading or ""),
                principle=principle.name,
                intruder=intruder[1].name,
                sentence=sentence,
            )
        )
    return found


def find_optional_example_leakage(
    heading: str,
    text: str,
    tip: Mapping[str, Any] | None = None,
    connectives: Sequence[str] = (),
    language: str = "en",
) -> list[OptionalExampleLeakage]:
    """A section that offers alternatives but argues for only one of them.

    The options are read from the sentences that list them - an enumeration
    joined by "or" naming two or more different things. If the causal sentence
    is about exactly one of those, and the heading itself is not about that
    thing, and the sentence never admits the condition, then most readers of
    this section have been given a reason that does not apply to them.
    """

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(str(text or "")) if s.strip()]
    heading_entities = entities_in(f"{heading} {(tip or {}).get('title', '')}")

    options: set[str] = set()
    for sentence in sentences:
        lowered = sentence.lower()
        if " or " not in lowered and " o " not in f" {lowered} ":
            continue
        named = entities_in(sentence)
        if len(named) >= 2:
            options |= named
    options -= heading_entities
    if len(options) < 2:
        return []

    markers = CONDITIONAL_MARKERS_ES if language == "es" else CONDITIONAL_MARKERS
    found: list[OptionalExampleLeakage] = []
    for sentence in _causal_sentences(text, connectives):
        lowered = f" {sentence.lower()} "
        if any(marker in lowered for marker in markers):
            continue
        subject = required_entity(sentence)
        if subject is None or subject.name in heading_entities:
            continue
        if subject.name not in options:
            continue
        found.append(
            OptionalExampleLeakage(
                heading=str(heading or ""),
                options=sorted(options),
                used=subject.name,
                sentence=sentence,
            )
        )
    return found


def condition_sentence(sentence: str, option: str, language: str = "en") -> str:
    """Rewrite a one-option explanation as the conditional it really is.

    The honest form of "a reflection adds depth" in a section that also offers
    a plant and a lamp is "if you choose the mirror, a reflection adds depth".
    Nothing is lost: the reason is still there, and now it is attached to the
    case it covers.
    """

    body = str(sentence or "").strip()
    if not body:
        return body
    label = option.replace("_", " ")
    lead = (
        f"Si eliges el {label}, " if language == "es" else f"If you choose the {label}, "
    )
    return lead + body[0].lower() + body[1:]


def summarise(
    contamination: Iterable[PrincipleContamination],
    leakage: Iterable[OptionalExampleLeakage],
) -> dict[str, Any]:
    contamination, leakage = list(contamination), list(leakage)
    return {
        "primary_concept_contamination_count": len(contamination),
        "primary_concept_contamination": [c.to_dict() for c in contamination],
        "optional_example_leakage_count": len(leakage),
        "optional_example_leakage": [l.to_dict() for l in leakage],
    }
