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
            # Deliberately not bare "even": "even though its footprint never
            # changed" is not a sentence about balance, and treating it as
            # one is why run 44's furniture-footprint explanation walked into
            # the balance section at a contamination count of zero.
            "equilibrium", "anchor", "anchors", "counterweight",
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
        name="focal_point_layout",
        triggers=(
            "focal point", "focal", "work outward", "work out from",
            "start from the", "layout", "arrangement", "arrange",
            "furniture placement", "place the largest",
        ),
        vocabulary=(
            "focal point", "focal", "fireplace", "the view", "facing",
            "faces", "face the", "orient", "oriented", "orientation",
            "outward", "outwards", "largest seat", "layout", "arrangement",
            "arrange", "arranged", "placement", "starts with", "begin with",
            "begins with", "work outward",
        ),
    ),
    Principle(
        name="statement_piece_scale",
        triggers=(
            "one large", "one big", "single large", "statement piece",
            "fewer larger", "one generous", "buy one bigger",
        ),
        vocabulary=(
            "single", "one piece", "one large", "one big", "statement",
            "generous", "fewer", "larger", "small ones", "many small",
            "three medium", "busier", "busy", "count", "fragment",
            "fragmented", "fragmentation", "one object",
        ),
    ),
    Principle(
        name="window_dressing",
        triggers=(
            "curtain", "curtains", "drape", "drapes", "blind", "blinds",
            "valance", "sheer", "window treatment",
        ),
        vocabulary=(
            "curtain", "curtains", "drape", "drapes", "fabric", "rod",
            "track", "hem", "panel", "panels", "blind", "blinds", "sheer",
            "pooling", "puddle", "hang the fabric", "hanging the fabric",
        ),
    ),
    Principle(
        name="window_daylight",
        # Deliberately not "daylight" or "light": a heading about daylight in
        # general is lighting advice and belongs to light_reflection. This
        # principle is the window itself - what stands in front of the glass.
        triggers=("window", "windows", "windowsill", "the glass"),
        vocabulary=(
            "window", "windows", "windowsill", "sill", "glass", "pane",
            "daylight", "sunlight", "natural light", "outside", "the view",
            "block", "blocks", "blocked", "blocking", "obstruct",
            "obstructed", "obstructs", "in front of", "let in", "lets in",
            "letting in",
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
    # Curtain advice is explained by height, by colour and by light; a
    # heading that says "hang" picks vertical_emphasis before it picks
    # curtains, so the two have to be able to borrow each other's language.
    "vertical_emphasis": frozenset({"sightline_depth", "window_dressing"}),
    "window_dressing": frozenset({
        "vertical_emphasis", "light_reflection", "color_continuity",
        "window_daylight",
    }),
    "corner_treatment": frozenset({"light_reflection", "floor_visibility"}),
    # A window is where the daylight comes from, so a window section may
    # reason about daylight - and it does, through this principle's own
    # vocabulary. It may not reason about lamps: "light the perimeter with
    # lamps" is a different piece of advice, and run 44 ended "do not block
    # the window" with exactly that. So light_reflection is not listed here.
    "window_daylight": frozenset({"sightline_depth"}),
    "focal_point_layout": frozenset({"sightline_depth"}),
    # Where you start a layout and how many objects you own are different
    # questions; statement_piece_scale is not compatible with either.
    "statement_piece_scale": frozenset({"clutter_editing"}),
    "clutter_editing": frozenset({"statement_piece_scale"}),
}

#: Which principle each mechanism family in :mod:`vidfactory.title_alignment`
#: is an explanation *of*.
#:
#: The vocabulary check below reads the sentence that was written. This reads
#: the family it came from, which is a fact rather than an inference, and it
#: is the half that holds when the repair simply rephrases: run 44's balance
#: section refused "oversized furniture ... narrows the walking paths" and
#: then accepted "a sofa that is too big for the room steals the floor around
#: it" from the same family, because the second wording happens to contain
#: none of the first one's words. A family is refused as a family.
MECHANISM_PRINCIPLES: dict[str, str] = {
    "furniture_footprint_scale": "furniture_footprint",
    "statement_piece_scale": "statement_piece_scale",
    "less_clutter": "clutter_editing",
    "restraint": "clutter_editing",
    "concealment": "clutter_editing",
    "clear_sightlines": "sightline_depth",
    "vertical_emphasis": "vertical_emphasis",
    "vertical_storage": "vertical_emphasis",
    "visible_floor": "floor_visibility",
    "continuous_flooring": "floor_visibility",
    "rug_scale": "floor_visibility",
    "light_distribution": "light_reflection",
    "more_light_sources": "light_reflection",
    "layered_light": "light_reflection",
    "warm_low_light": "light_reflection",
    "colour_temperature": "light_reflection",
    "mirrors_and_reflection": "light_reflection",
    "reflection": "light_reflection",
    "pale_surfaces": "color_continuity",
    "low_contrast_edges": "color_continuity",
    "daylight": "window_daylight",
    "unobstructed_windows": "window_daylight",
    # Every sentence in this family is about hanging fabric - "the fabric
    # high", "mounting the track", "beyond the frame". It is curtain advice
    # that happens to be *named* after the window, and run 44 closed "do not
    # block the window" with it.
    "window_geometry": "window_dressing",
    "furniture_placement": "focal_point_layout",
    "window_dressing": "window_dressing",
    "visual_balance": "visual_weight_balance",
}


def mechanism_principle(family: str) -> str:
    return MECHANISM_PRINCIPLES.get(str(family or ""), "")


def mechanism_fits(heading: str, family: str, tip: Mapping[str, Any] | None = None) -> bool:
    """May this section be explained by this mechanism family at all?

    Unknown families are allowed: the map covers the ones that have actually
    caused a contamination, and refusing everything unmapped would silently
    starve the repair pass.
    """

    principle = primary_principle(heading, tip)
    other = mechanism_principle(family)
    if principle is None or not other:
        return True
    return is_compatible(principle.name, other)


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
    #: "leakage" - the explanation covers one of the options offered.
    #: "false_condition" - it was conditioned on something never offered.
    kind: str = "leakage"

    def explain(self) -> str:
        if self.kind == "false_condition":
            offered = ", ".join(sorted(self.options)) or "no alternatives"
            return (
                f"the explanation is conditioned on {self.used}, which the "
                f"section never offers (it offers {offered})"
            )
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
            "kind": self.kind,
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


def _offered_options(
    heading: str, text: str, tip: Mapping[str, Any] | None = None
) -> set[str]:
    """The alternatives the section actually puts on the table.

    An enumeration joined by "or" naming two or more different things, less
    whatever the heading is already about - a section called "leave the
    corners resolved" offering a plant, a lamp, a mirror or a chair offers
    four options, not five.
    """

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(str(text or "")) if s.strip()]
    options: set[str] = set()
    for sentence in sentences:
        lowered = sentence.lower()
        if " or " not in lowered and " o " not in f" {lowered} ":
            continue
        named = entities_in(sentence)
        if len(named) >= 2:
            options |= named
    return options - entities_in(f"{heading} {(tip or {}).get('title', '')}")


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

    heading_entities = entities_in(f"{heading} {(tip or {}).get('title', '')}")
    options = _offered_options(heading, text, tip)
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


#: What :func:`condition_sentence` writes, so a wrong one can be found again.
_CONDITION_RE = re.compile(r"\bif you choose the ([a-z][a-z ]{1,28}?)\s*,", re.I)
_CONDITION_RE_ES = re.compile(r"\bsi eliges el ([a-zá-ú][a-zá-ú ]{1,28}?)\s*,", re.I)


def find_false_conditioning(
    heading: str,
    text: str,
    tip: Mapping[str, Any] | None = None,
    language: str = "en",
) -> list[OptionalExampleLeakage]:
    """A conditional clause offering a choice the section never offered.

    :func:`condition_sentence` is honest only when the option it names is one
    the section actually put on the table. Run 44 shipped

        Aim for at least three light sources per room
        ... something low or wall-mounted for atmosphere ...
        If you choose the wall finish, light on the walls makes the
        boundaries of the room visible ...

    at ``optional_example_leakage_count = 0``, because the leakage check had
    repaired it and its own repair satisfied it. The section offers a ceiling
    light, a lamp and a wall-mounted fitting; it never offers a wall finish.
    ``wall-mounted`` was read as the wall itself, and the reader is now being
    asked to choose something that was never a choice.

    The trigger word is fixed at source - :data:`vidfactory.entities.
    VisualEntity.excluded` keeps ``wall-mounted`` out of ``wall_finish`` - and
    this is the net under it, because the conditioner will always be able to
    name something the paragraph does not offer.
    """

    pattern = _CONDITION_RE_ES if language == "es" else _CONDITION_RE
    matches = list(pattern.finditer(str(text or "")))
    if not matches:
        return []

    offered = _offered_options(heading, text, tip)
    heading_entities = entities_in(f"{heading} {(tip or {}).get('title', '')}")
    allowed = offered | heading_entities

    found: list[OptionalExampleLeakage] = []
    for match in matches:
        named = required_entity(match.group(1))
        if named is None or named.name in allowed:
            continue
        sentence = next(
            (
                s.strip()
                for s in _SENTENCE_SPLIT.split(str(text or ""))
                if match.group(0).lower() in s.lower()
            ),
            match.group(0),
        )
        found.append(
            OptionalExampleLeakage(
                heading=str(heading or ""),
                options=sorted(offered),
                used=named.name,
                sentence=sentence,
                kind="false_condition",
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
    """Both are errors. False conditioning arrives inside ``leakage``,
    because it is the same defect seen after a repair rather than before."""

    contamination, leakage = list(contamination), list(leakage)
    return {
        "primary_concept_contamination_count": len(contamination),
        "primary_concept_contamination": [c.to_dict() for c in contamination],
        "optional_example_leakage_count": len(leakage),
        "optional_example_leakage": [l.to_dict() for l in leakage],
    }
