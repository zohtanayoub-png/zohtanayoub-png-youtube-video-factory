"""Does the paragraph argue *for* the advice in its own heading?

:mod:`vidfactory.title_alignment` decides whether an idea can deliver the
title's promise. :mod:`vidfactory.causal_alignment` decides whether the written
paragraph explains that it does. Both passed on run 16, and run 16 still shipped
this:

    Buy one bigger thing instead of three medium things
    ... Oversized pieces eat visible floor area and narrow the walking paths,
    so a small room feels cramped even though its footprint never changed.

and this:

    Buy a rug that is genuinely too big rather than slightly too small
    ... A piece that is too big for the room steals the floor around it, so
    what is left over feels cramped even though nothing else changed.

Both paragraphs scored 1.00 for causal alignment, because both *do* state a
mechanism, a connective and the promised outcome. What neither check could see
is that the mechanism argues against the heading. The causal repair had one
explanation per mechanism family and no notion of which way it pointed, so a
cautionary sentence about the mistake got appended to advice recommending the
opposite.

So this module models the missing thing: **direction**.

Each item is read as

    recommended_action  ->  mechanism  ->  desired_outcome

with a ``thing_to_avoid`` alongside it, and a contradiction is the specific,
deterministic pattern of a sentence claiming that *the recommended thing causes
the harm the title is trying to prevent*. "Go bigger with the rug" followed by
"too big steals the floor and feels cramped" is a contradiction. "Go bigger with
the rug" followed by "too small leaves the furniture floating" is not - it
argues for the advice by describing the mistake, which is exactly what good
decorating writing does.

The check is keyword-deterministic on purpose. It runs on every render, it must
never need a model, and a rule you can read is a rule you can argue with when it
gets something wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from .logging_utils import get_logger

log = get_logger("CONTRA")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

#: Phrases that split a heading into "do this" and "not that". Everything
#: before one of these is the recommendation; everything after is the mistake.
#: "Buy one bigger thing INSTEAD OF three medium things".
_CONTRAST_MARKERS: tuple[str, ...] = (
    " instead of ", " rather than ", " not ", " over ", " and not ",
    " never ", " but not ", " en lugar de ", " en vez de ", " y no ",
    " no ", " antes que ",
)


@dataclass(frozen=True)
class Axis:
    """One property an item can recommend more of, or less of.

    ``more`` and ``less`` are the two poles. A heading that lands on a pole
    takes a stance; a sentence that pairs a pole with a harm makes a claim.
    Both sides are needed, because the contradiction is the disagreement
    between them, not anything either one says alone.
    """

    name: str
    more: tuple[str, ...]
    less: tuple[str, ...]


#: The properties that decorating advice actually argues about, and that run 16
#: managed to argue about in both directions inside one paragraph.
AXES: tuple[Axis, ...] = (
    Axis(
        "scale",
        more=(
            "bigger", "larger", "large", "oversized", "over-sized", "too big",
            "generously sized", "generously scaled", "generous", "go big",
            "big enough", "large enough", "wide enough", "substantial",
            "statement piece", "one big", "one large",
        ),
        less=(
            "smaller", "undersized", "under-sized", "too small", "tiny",
            "small enough", "petite", "skimpy", "meagre", "meager",
        ),
    ),
    Axis(
        "brightness",
        more=(
            "brighter", "bright", "pale", "light color", "light colour",
            "lighter", "well lit", "well-lit", "daylight", "more light",
        ),
        less=("darker", "dark", "dim", "gloomy", "shadowy", "unlit"),
    ),
    Axis(
        "openness",
        more=("open", "opens up", "openness", "airy", "unobstructed", "float"),
        less=("closed", "enclosed", "blocked", "boxed", "walled off"),
    ),
    Axis(
        "clarity",
        more=(
            "clear", "clears", "cleared", "uncluttered", "declutter",
            "decluttered", "tidy", "edited", "pared back", "minimal",
        ),
        less=("cluttered", "clutter", "busy", "crowded", "messy"),
    ),
    Axis(
        "height",
        more=("taller", "tall", "high", "higher", "full height", "to the ceiling"),
        less=("lower", "low", "shorter", "short", "waist height"),
    ),
    Axis(
        "fewer_objects",
        more=("fewer", "one instead of", "a single", "just one", "one piece"),
        less=("several", "multiple", "a cluster of", "lots of", "many small"),
    ),
)

#: Phrases that mean the harm right after them is being ruled out rather than
#: claimed. "The eye reads one connected area INSTEAD OF scattered furniture"
#: names a harm in order to deny it, which is the opposite of asserting it.
_HARM_DENIED_BY: tuple[str, ...] = (
    "instead of", "rather than", "not ", "no ", "never", "avoids", "avoid",
    "stops", "stop", "without", "prevents", "prevent", "less ", "away from",
    "en lugar de", "en vez de", "sin ", "evita", "evitar", "deja de",
)

#: How far back to look for one of those. A denial sits immediately before the
#: harm it denies; anything further away is a different clause.
_DENIAL_WINDOW = 24


#: Los mismos ejes en español, para que el guion en español no pueda
#: contradecirse de la misma forma.
AXES_ES: tuple[Axis, ...] = (
    Axis(
        "scale",
        more=("más grande", "más grandes", "grande", "generoso", "generosa",
              "sobredimensionad", "demasiado grande", "lo bastante grande",
              "una sola pieza grande"),
        less=("más pequeñ", "pequeñ", "demasiado pequeñ", "justo", "escaso",
              "se queda corto", "se queda corta"),
    ),
    Axis(
        "brightness",
        more=("más claro", "más clara", "claro", "clara", "luminoso", "luminosa",
              "más luz", "luz natural"),
        less=("más oscuro", "más oscura", "oscuro", "oscura", "sombrío", "penumbra"),
    ),
    Axis(
        "clarity",
        more=("despejado", "despejada", "despejar", "ordenado", "ordenada",
              "sin desorden", "recogido"),
        less=("desorden", "abarrotado", "abarrotada", "recargado", "recargada"),
    ),
    Axis(
        "height",
        more=("más alto", "más alta", "alto", "alta", "hasta el techo",
              "toda la altura"),
        less=("más bajo", "más baja", "bajo", "baja", "a media altura"),
    ),
)

#: What the title is trying to prevent. A sentence pairing one of these with a
#: pole of an axis is claiming that pole causes the harm.
HARMS: tuple[str, ...] = (
    "cramped", "boxed in", "feels smaller", "feel smaller", "reads as smaller",
    "look smaller", "looks smaller", "shrinks", "shrink the", "shrinking",
    "tighter", "eats", "eat visible", "eats visible", "eats into", "steals",
    "swallows", "narrows", "narrow the", "closes in", "closing in",
    "cluttered", "chaotic", "chopped", "chops", "fragments", "fragmented",
    "disconnected", "scattered", "cheap", "heavy", "oppressive", "claustrophobic",
    "dead space", "wasted", "reads flat", "flat and", "smaller than it",
)

HARMS_ES: tuple[str, ...] = (
    "agobiante", "apretado", "apretada", "encoge", "empequeñece",
    "se come", "se comen", "roba", "estrecha", "estrechan", "cierra",
    "abarrotado", "abarrotada", "recargado", "caótico", "fragmenta",
    "desconectad", "disperso", "dispersa", "más pequeñ de lo que",
    "espacio muerto", "desaprovechad",
)

_HARMS_BY_LANGUAGE: dict[str, tuple[str, ...]] = {"en": HARMS, "es": HARMS_ES}
_AXES_BY_LANGUAGE: dict[str, tuple[Axis, ...]] = {"en": AXES, "es": AXES_ES}


def axes_for(language: str = "en") -> tuple[Axis, ...]:
    return _AXES_BY_LANGUAGE.get(language, AXES)


def harms_for(language: str = "en") -> tuple[str, ...]:
    return _HARMS_BY_LANGUAGE.get(language, HARMS)


def _normalise(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9áéíóúüñ ]+', ' ', str(text or '').lower())} "


def _first_hit(haystack: str, phrases: Sequence[str]) -> str | None:
    """The first phrase that starts a word in ``haystack``.

    Anchored at the start of a word and free at the end. The start anchor is
    what stops "eats" matching inside "seats" - which flagged a perfectly good
    rug sentence as a contradiction - while the free end keeps the Spanish
    stems working, where "pequeñ" has to match "pequeña" and "pequeño", and
    lets "fragment" match "fragmentation".
    """

    for phrase in phrases:
        text = phrase.strip()
        if text and re.search(rf"\b{re.escape(text)}", haystack):
            return text
    return None


def _harm_is_denied(haystack: str, harm: str) -> bool:
    """Is this harm being ruled out rather than blamed on something?"""

    match = re.search(rf"\b{re.escape(harm)}", haystack)
    if not match:
        return False
    lead = haystack[max(0, match.start() - _DENIAL_WINDOW) : match.start()]
    return any(marker in lead for marker in _HARM_DENIED_BY)


def split_recommendation(heading: str, language: str = "en") -> tuple[str, str]:
    """Separate what a heading tells you to do from what it tells you to avoid.

    ``"Buy one bigger thing instead of three medium things"`` becomes
    ``("buy one bigger thing", "three medium things")``. A heading with no
    contrast marker is all recommendation and avoids nothing.
    """

    padded = _normalise(heading)
    for marker in _CONTRAST_MARKERS:
        if marker in padded:
            head, _, tail = padded.partition(marker)
            return head.strip(), tail.strip()
    return padded.strip(), ""


@dataclass
class AdviceDirection:
    """Which way one item's advice points.

    This is the structure the contradiction check needs and the report prints:
    what the viewer is told to do, what they are told to avoid, the mechanism
    that connects the two, and the outcome the title promised.
    """

    heading: str = ""
    recommended_action: str = ""
    thing_to_avoid: str = ""
    mechanism: str = ""
    desired_outcome: str = ""
    #: Axis name -> +1 when the heading recommends more of it, -1 for less.
    stance: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_action": self.recommended_action,
            "thing_to_avoid": self.thing_to_avoid,
            "mechanism": self.mechanism,
            "desired_outcome": self.desired_outcome,
            "stance": dict(self.stance),
        }


def read_direction(
    heading: str,
    mechanism: str = "",
    outcome: str = "",
    language: str = "en",
) -> AdviceDirection:
    """Work out which way a heading's advice points, axis by axis.

    The stance comes from the recommended half of the heading only. "Buy a rug
    that is genuinely too big rather than slightly too small" recommends more
    scale; reading the whole string at once would find both poles and conclude
    nothing.
    """

    recommended, avoided = split_recommendation(heading, language)
    direction = AdviceDirection(
        heading=str(heading or ""),
        recommended_action=recommended,
        thing_to_avoid=avoided,
        mechanism=mechanism,
        desired_outcome=outcome,
    )
    for axis in axes_for(language):
        more = _first_hit(f" {recommended} ", axis.more)
        less = _first_hit(f" {recommended} ", axis.less)
        if more and not less:
            direction.stance[axis.name] = 1
        elif less and not more:
            direction.stance[axis.name] = -1
        elif not more and not less and avoided:
            # The heading only named the mistake ("...instead of a tiny rug"),
            # so the recommendation is the opposite pole of whatever it avoids.
            padded_avoid = f" {avoided} "
            if _first_hit(padded_avoid, axis.less):
                direction.stance[axis.name] = 1
            elif _first_hit(padded_avoid, axis.more):
                direction.stance[axis.name] = -1
    return direction


@dataclass
class Contradiction:
    """One sentence that argues against the advice it is supposed to support."""

    index: int = 0
    heading: str = ""
    axis: str = ""
    recommends: str = ""
    sentence: str = ""
    trigger: str = ""
    harm: str = ""

    def explain(self) -> str:
        return (
            f"the heading recommends {self.recommends} {self.axis}, but the "
            f"paragraph says '{self.trigger}' leads to '{self.harm}'"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "heading": self.heading,
            "axis": self.axis,
            "recommends": self.recommends,
            "trigger": self.trigger,
            "harm": self.harm,
            "sentence": self.sentence[:200],
            "why": self.explain(),
        }


def find_contradictions(
    heading: str,
    text: str,
    language: str = "en",
    direction: AdviceDirection | None = None,
) -> list[Contradiction]:
    """Every sentence in ``text`` that argues against ``heading``.

    A contradiction needs three things in one sentence: a pole of an axis the
    heading has taken a stance on, a harm, and the stance pointing the other
    way. Requiring all three in the same sentence is what keeps a paragraph
    that legitimately contrasts the advice with the mistake - the normal shape
    of decorating writing - from being flagged.
    """

    direction = direction or read_direction(heading, language=language)
    if not direction.stance:
        return []

    harms = harms_for(language)
    found: list[Contradiction] = []
    for sentence in _SENTENCE_SPLIT.split(str(text or "")):
        if not sentence.strip():
            continue
        padded = _normalise(sentence)
        harm = _first_hit(padded, harms)
        if not harm or _harm_is_denied(padded, harm):
            continue
        for axis in axes_for(language):
            stance = direction.stance.get(axis.name)
            if not stance:
                continue
            # A sentence blaming the pole the heading recommends is the bug.
            blamed = axis.more if stance > 0 else axis.less
            defended = axis.less if stance > 0 else axis.more
            trigger = _first_hit(padded, blamed)
            if not trigger:
                continue
            # ...unless the sentence also names the opposite pole, in which
            # case it is drawing the comparison rather than reversing it.
            if _first_hit(padded, defended):
                continue
            found.append(
                Contradiction(
                    heading=str(heading or ""),
                    axis=axis.name,
                    recommends="more" if stance > 0 else "less",
                    sentence=sentence.strip(),
                    trigger=trigger.strip(),
                    harm=harm.strip(),
                )
            )
            break       # one finding per sentence is enough to reject it
    return found


def contradicts(heading: str, text: str, language: str = "en") -> bool:
    """Does this paragraph argue against its own heading?"""

    return bool(find_contradictions(heading, text, language))


@dataclass
class ContradictionReport:
    """What the editorial report says about self-contradicting sections."""

    items: list[Contradiction] = field(default_factory=list)
    directions: list[AdviceDirection] = field(default_factory=list)
    rewrites: int = 0
    replacements: int = 0

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def passed(self) -> bool:
        return not self.items

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_count": self.count,
            "contradictions_resolved_by_rewrite": self.rewrites,
            "contradictions_resolved_by_replacement": self.replacements,
            "contradictions": [item.to_dict() for item in self.items],
            "section_directions": [d.to_dict() for d in self.directions],
        }
