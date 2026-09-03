"""What a piece of advice is *about*, as distinct from how it works.

Run 22 shipped this:

    Hang art at eye level and scale it to the furniture
    ... Hanging the fabric high and wide leaves the glass itself uncovered, so
    more daylight reaches the room and the wall reads taller than it measures.

Causal alignment scored it 1.00 and the contradiction check found nothing,
because both were right on their own terms: the sentence does state a
mechanism, does carry a connective, does claim the promised outcome, and does
argue the same direction as the heading. It is simply about curtains, in a
section about pictures.

The gap is that a mechanism is not a subject. ``vertical_emphasis`` is equally
true of a curtain rod, a bookcase and a gallery wall, so matching on the
mechanism alone lets any of their explanations land on any of them. An
explanation has to agree with the section on *both*:

    mechanism  +  concept

so a curtain explanation is available to curtain advice and to nothing else.

The vocabularies below are deliberately about physical things a decorating
video points a camera at - art, curtains, rugs, lamps, mirrors, storage - and
not about abstractions like "scale" or "proportion", which genuinely do belong
to every subject and would flag everything if they were listed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .logging_utils import get_logger

log = get_logger("CONCEPT")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Concept:
    """One family of physical things a decorating idea can be about."""

    name: str
    words: tuple[str, ...]


#: Ordered by specificity where two could overlap: "wall art" is art, not wall.
CONCEPTS: tuple[Concept, ...] = (
    Concept("wall_art", (
        "art", "artwork", "print", "poster", "canvas", "gallery wall",
        "picture frame", "framed", "painting on the wall", "wall art",
    )),
    Concept("window_dressing", (
        "curtain", "curtains", "drape", "drapes", "blind", "blinds",
        "curtain rod", "the track", "valance", "sheer", "window", "windows",
        "the glass", "windowsill", "sill",
    )),
    Concept("rug", ("rug", "rugs", "carpet", "runner", "area rug")),
    Concept("lighting", (
        "lamp", "lamps", "sconce", "pendant", "chandelier", "bulb", "bulbs",
        "downlight", "light fitting", "light fixture", "lampshade", "dimmer",
        "light source", "light sources", "ceiling light", "overhead light",
        "lighting",
    )),
    Concept("mirror", ("mirror", "mirrors", "mirrored")),
    Concept("storage", (
        "storage", "shelf", "shelves", "shelving", "bookcase", "cabinet",
        "cupboard", "wardrobe", "basket", "baskets", "drawer", "drawers",
    )),
    Concept("seating", (
        "sofa", "couch", "armchair", "chair", "chairs", "seating", "ottoman",
        "sectional", "loveseat",
    )),
    Concept("tables", ("coffee table", "side table", "console", "dining table", "nightstand")),
    Concept("flooring", ("flooring", "floorboard", "floorboards", "floor finish", "tile", "tiles", "laminate")),
    Concept("wall_finish", (
        "paint", "painted", "wall colour", "wall color", "trim", "skirting",
        "moulding", "molding", "wallpaper", "panelling", "paneling",
    )),
    Concept("greenery", ("plant", "plants", "tree", "foliage", "flowers", "branches")),
    Concept("bedding", ("bed", "bedding", "duvet", "headboard", "pillow", "pillows", "cushion", "cushions")),
)

#: Concepts that are close enough to share language without it reading as a
#: mistake. A mirror hung to bounce daylight is legitimately about the window
#: too, and lighting advice legitimately talks about daylight.
COMPATIBLE: dict[str, frozenset[str]] = {
    "mirror": frozenset({"window_dressing", "lighting", "wall_art"}),
    "lighting": frozenset({"window_dressing"}),
    "window_dressing": frozenset({"lighting"}),
    "wall_art": frozenset({"mirror"}),
    "seating": frozenset({"tables", "rug"}),
    "tables": frozenset({"seating", "rug"}),
    "rug": frozenset({"seating", "tables", "flooring"}),
    "flooring": frozenset({"rug"}),
    "bedding": frozenset({"seating"}),
}


def _normalise(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9áéíóúüñ ]+', ' ', str(text or '').lower())} "


def concepts_in(text: str) -> set[str]:
    """Every concept the text names, matched on whole words."""

    haystack = _normalise(text)
    found: set[str] = set()
    for concept in CONCEPTS:
        for word in concept.words:
            if re.search(rf"\b{re.escape(word)}\b", haystack):
                found.add(concept.name)
                break
    return found


def subject_concepts(heading: str, tip: Mapping[str, Any] | None = None) -> set[str]:
    """What this section is about: its heading, and its idea's title and tags.

    Deliberately not the body. An idea's ``why`` and ``how`` mention whatever
    they need to - art advice may well name the sofa the picture hangs over -
    and judging the subject by them would make almost every section about
    everything.
    """

    parts = [str(heading or "")]
    if tip:
        parts.append(str(tip.get("title", "")))
        parts.extend(str(t) for t in tip.get("tags", []) or [])
    return concepts_in(" ".join(parts))


def is_compatible(subject: Iterable[str], other: Iterable[str]) -> bool:
    """May a sentence about ``other`` appear in a section about ``subject``?"""

    subject, other = set(subject), set(other)
    if not subject or not other or subject & other:
        return True
    for name in subject:
        if other & COMPATIBLE.get(name, frozenset()):
            return True
    return False


@dataclass
class Contamination:
    """One sentence that is about something the section is not."""

    index: int = 0
    heading: str = ""
    subject: list[str] = field(default_factory=list)
    intruder: list[str] = field(default_factory=list)
    sentence: str = ""

    def explain(self) -> str:
        return (
            f"the section is about {', '.join(sorted(self.subject)) or 'nothing specific'}"
            f" but this sentence is about {', '.join(sorted(self.intruder))}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "heading": self.heading,
            "subject": sorted(self.subject),
            "intruder": sorted(self.intruder),
            "sentence": self.sentence[:200],
            "why": self.explain(),
        }


def find_contamination(
    heading: str,
    text: str,
    tip: Mapping[str, Any] | None = None,
) -> list[Contamination]:
    """Sentences that discuss a concept this section is not about.

    Only sentences whose concepts are *entirely* foreign to the section are
    flagged. A sentence that mentions the section's own subject alongside
    something else is a normal comparison, not a transplant.
    """

    subject = subject_concepts(heading, tip)
    if not subject:
        return []

    found: list[Contamination] = []
    for sentence in _SENTENCE_SPLIT.split(str(text or "")):
        if not sentence.strip():
            continue
        mentioned = concepts_in(sentence)
        if not mentioned or is_compatible(subject, mentioned):
            continue
        found.append(
            Contamination(
                heading=str(heading or ""),
                subject=sorted(subject),
                intruder=sorted(mentioned - subject),
                sentence=sentence.strip(),
            )
        )
    return found


def explanation_fits(
    heading: str, explanation: str, tip: Mapping[str, Any] | None = None
) -> bool:
    """May this mechanism explanation be appended to this section?

    The prevention half of the same rule the validator enforces: an
    explanation about curtains never reaches an art section in the first
    place, rather than being detected once it is already in the script.
    """

    subject = subject_concepts(heading, tip)
    return is_compatible(subject, concepts_in(explanation))
