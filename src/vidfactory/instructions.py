"""The whole visual claim, not the noun inside it.

:mod:`vidfactory.entities` asks whether the object the sentence is about owns
the frame. Run 44 shows that this is necessary and not sufficient. It reported

    entity_grounding_failure_count  = 0
    entity_grounding_pass_percentage = 100%

over 93 grounded shots, and shipped:

* **Tip 14**, "paint the trim the same color as the walls" - colourful
  metallic ribbon strips filling the frame, flowers beside a wall, ornate
  architectural decoration. All three passed ``wall_finish``.
* **Tip 9**, "do not block the window" - a dragonfly sitting on a window, a
  kitchen faucet in front of a window. Both contain a window.

Nothing there is a scoring error. A dragonfly on a windowpane genuinely is a
frame containing a window, and nothing else displaces it, which is the only
question ``entities`` asks. The advice is not "show me a window": it is *keep
tall furniture away from the glass*, and a photograph can only demonstrate
that by showing a room, a window, and the relationship between the furniture
and the window. Presence is a property of one object. An instruction is a
property of a scene.

So a claim here has four parts, and they are the four parts of the advice:

    subject        the object entities.py already requires
    context        the kind of scene it has to be in
    relationship   what has to be true between them
    forbidden      the scenes that satisfy the subject and not the advice

``context`` and ``relationship`` are scored together as one set of positive
prompts rather than as two gates. Each prompt is a full sentence carrying
both - "a sofa placed clear of a bright living room window" is context *and*
relationship - because two independent CLIP margins multiply their false
positive rates, and the calibration behind ``ENTITY_DOMINANCE_FAIL`` already
puts a single margin's cost near eight percent of good footage. They are
separate fields because they are separate to write and separate to review,
not because they are separately measured.

The comparison is a margin, for the reason this codebase keeps rediscovering:
CLIP's classification softmax runs at a temperature of 100 and is
winner-take-all, and a broad prompt beats a specific one against almost any
photograph. What is different here, and what gives this a chance where the
bare-noun probe had none, is that **both sides are equally specific**. "A
dragonfly resting on a windowpane" and "a sofa placed clear of a bright living
room window" are the same kind of sentence about the same kind of picture. The
generality bias needs a generality gap to exploit.

Whether that is enough is a measurement, not an argument: ``vidfactory
instruction-check`` scores the exact run 44 failure classes and their valid
counterparts on real provider footage, and the numbers it prints are what
decides whether this layer stays as it is or is replaced by a heavier
verifier. Abstract advice declares no claim and is not gated, exactly as
abstract advice requires no entity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .logging_utils import get_logger

log = get_logger("CLAIM")

#: The same shape as ``ENTITY_MARGIN_*``: how far the best forbidden scene has
#: to beat the best statement of the claim before the frame counts as being
#: about the forbidden one.
CLAIM_MARGIN_LOW = 0.0
CLAIM_MARGIN_HIGH = 0.05

#: How much displacement is a failure. Provisional at 0.70 rather than the
#: entity gate's 0.80, and deliberately looser than the entity threshold in
#: the direction that matters: a claim is a harder thing to state than a noun,
#: so a frame has to lose more clearly before this rejects it. The real value
#: is whatever ``vidfactory instruction-check`` measures on the run 44 failure
#: classes; until that has run on a machine with a CLIP backend and a provider
#: key, this number is an assumption and is documented as one.
CLAIM_DOMINANCE_FAIL = 0.70


@dataclass(frozen=True)
class InstructionClaim:
    """What a shot has to *demonstrate*, not merely contain.

    ``triggers`` are matched against the shot's own narration chunk, like the
    entity triggers and for the same reason: a passing mention of a window in
    rug advice must not start demanding a window layout.

    ``entity`` names the object :mod:`vidfactory.entities` already requires,
    so the two layers agree about the subject rather than disagreeing about
    it. ``forbidden`` are the scenes actually observed passing the entity gate
    while failing the advice - the dragonfly, the faucet, the ribbons - and
    nothing speculative belongs in it.
    """

    name: str
    label: str
    triggers: tuple[str, ...]
    entity: str
    context: tuple[str, ...]
    relationship: tuple[str, ...]
    forbidden: tuple[str, ...]
    queries: tuple[str, ...]
    #: Searches that reproduce the failure this claim exists to catch, so
    #: ``vidfactory instruction-check`` can measure it on real footage instead
    #: of waiting for a thirty minute render to show it again. Probe input
    #: only; nothing in the pipeline searches with these.
    observed_failures: tuple[str, ...] = ()

    @property
    def positives(self) -> tuple[str, ...]:
        return (*self.relationship, *self.context)


CLAIMS: tuple[InstructionClaim, ...] = (
    # ------------------------------------------------------------------
    # Run 44, tip 9. A dragonfly on a windowpane and a kitchen faucet in
    # front of a window both contain a window and neither shows a room whose
    # furniture is clear of it.
    # ------------------------------------------------------------------
    InstructionClaim(
        name="window_layout",
        label="furniture kept clear of the window",
        triggers=(
            "block the window", "blocking the window", "in front of the window",
            "in front of the glass", "window wall", "windowsill height",
            "under the window", "below the window", "away from the window",
            "obstruct the window", "clear the window", "clear of the window",
        ),
        entity="window",
        context=(
            "a furnished living room with a window in the wall",
            "a residential living room interior lit by a window",
        ),
        relationship=(
            "a sofa placed clear of a bright living room window",
            "low furniture standing beneath a living room window",
            "an unobstructed window in a furnished living room",
            "a living room where nothing tall stands in front of the window",
        ),
        forbidden=(
            "a close-up of an insect resting on a windowpane",
            "a kitchen sink and tap in front of a window",
            "a close-up of a glass pane with no room visible",
            "the outside of a building seen from the street",
            "a close-up of a plant on a windowsill",
        ),
        queries=(
            "living room sofa away from window natural light",
            "low furniture under living room window",
            "unobstructed window bright living room interior",
            "living room layout window daylight",
        ),
        observed_failures=(
            "dragonfly insect on window",
            "kitchen faucet in front of window",
            "window glass pane close up",
        ),
    ),
    # ------------------------------------------------------------------
    # Run 44, tip 14. Metallic ribbon strips, flowers beside a wall and
    # ornate carved decoration all passed wall_finish.
    # ------------------------------------------------------------------
    InstructionClaim(
        name="wall_trim_paint",
        label="painted wall and trim in one colour",
        triggers=(
            "paint the trim", "trim the same color", "trim the same colour",
            "skirting", "baseboard", "moulding", "molding", "door casing",
            "paint the walls", "same color as the walls",
            "same colour as the walls", "architrave",
        ),
        entity="wall_finish",
        context=(
            "an interior wall of a residential room",
            "a plain painted room interior",
        ),
        relationship=(
            "an interior wall with its trim painted the same colour",
            "painted skirting board along the bottom of a plain wall",
            "a painted door casing against a plain interior wall",
            "a person painting interior wall trim with a brush",
        ),
        forbidden=(
            "colourful metallic ribbons and party streamers",
            "a close-up of colourful printed fabric",
            "an ornate carved decorative pattern",
            "flowers arranged in front of a wall",
            "a patterned tiled surface",
            "a close-up of a textured surface with no room visible",
        ),
        queries=(
            "painted wall trim same color as wall interior",
            "white skirting board painted wall living room",
            "person painting interior door frame roller",
            "plain painted interior wall and baseboard",
        ),
        observed_failures=(
            "colorful ribbons streamers decoration",
            "ornate decorative carved pattern",
            "flowers in front of wall",
        ),
    ),
    # ------------------------------------------------------------------
    # A rug is not rug advice. Run 25 shipped a rug in shot under advice
    # about the rug's relationship to the seating, which is what the advice
    # is actually about.
    # ------------------------------------------------------------------
    InstructionClaim(
        name="rug_sizing",
        label="a rug sized against the furniture on it",
        triggers=(
            "front legs", "all four legs", "rug wide enough", "rug large enough",
            "too small to reach", "rug big enough", "size the rug",
            "rug under the sofa", "rug reaches",
        ),
        entity="rug",
        context=(
            "a living room floor with an area rug",
            "a furnished living room seen from across the room",
        ),
        relationship=(
            "a large area rug with the front legs of a sofa standing on it",
            "a rug wide enough to reach the seating around it",
            "a rug spanning the floor beneath a coffee table and sofa",
        ),
        forbidden=(
            "a small rug alone on a bare floor",
            "a close-up of carpet pile with no furniture visible",
            "a bare floor with no rug",
            "a rolled up rug",
            "indoor potted plants on a floor",
        ),
        queries=(
            "large area rug under sofa front legs living room",
            "rug reaching sofa and coffee table interior",
            "correctly sized living room rug seating",
        ),
        observed_failures=(
            "carpet texture close up",
            "indoor potted plants on floor",
            "small rug bare floor",
        ),
    ),
    # ------------------------------------------------------------------
    # "Three light sources" is a claim about how many, and a single lamp
    # satisfies every noun in it.
    # ------------------------------------------------------------------
    InstructionClaim(
        name="layered_lighting",
        label="more than one source of light in the room",
        triggers=(
            "three light sources", "light sources", "layered lighting",
            "layers of light", "pools of light", "more than one lamp",
            "several lamps", "light the perimeter", "perimeter with lamps",
            "not just the middle of the room",
        ),
        entity="lighting",
        context=(
            "a residential living room in the evening",
            "a furnished room interior with lamps",
        ),
        relationship=(
            "a living room with several lamps lit at the same time",
            "a room with separate pools of light from more than one lamp",
            "a lit table lamp and a lit floor lamp in one room",
        ),
        forbidden=(
            "a close-up of a single light bulb",
            "one ceiling light in an otherwise dark room",
            "a close-up of a light fitting with no room visible",
            "a decorative object hanging on a wall",
            "an outdoor street light at night",
        ),
        queries=(
            "living room several lamps lit evening layered lighting",
            "table lamp and floor lamp lit living room",
            "warm layered lighting living room interior evening",
        ),
        observed_failures=(
            "light bulb close up",
            "single ceiling light dark room",
            "decorative wall hanging",
        ),
    ),
)

BY_NAME: dict[str, InstructionClaim] = {c.name: c for c in CLAIMS}


def _normalise(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9 ]+', ' ', str(text or '').lower())} "


def required_claim(text: str) -> InstructionClaim | None:
    """The claim this shot has to demonstrate, or ``None`` when it makes none.

    The claim named *first*, on the same reasoning as
    :func:`vidfactory.entities.required_entity`: a sentence leads with what it
    is about and mentions the landmark afterwards.
    """

    haystack = _normalise(text)
    if not haystack.strip():
        return None
    scored: list[tuple[int, int, InstructionClaim]] = []
    for claim in CLAIMS:
        positions = [
            m.start()
            for word in claim.triggers
            if (m := re.search(rf"\b{re.escape(word)}\b", haystack))
        ]
        if positions:
            scored.append((min(positions), -len(positions), claim))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[0][2]


def claim_prompts(claim: InstructionClaim) -> tuple[list[str], int]:
    """(every prompt to encode, where the forbidden scenes start)."""

    return [*claim.positives, *claim.forbidden], len(claim.positives)


def repair_queries(text: str, base_query: str = "") -> list[str]:
    """Searches phrased around the whole claim rather than around the object.

    Searching for the object is what the entity repair does, and it is why
    "window" came back with a dragonfly on one. These name the relationship.
    """

    claim = required_claim(text)
    if claim is None:
        return [q for q in (base_query,) if q]
    queries = list(claim.queries)
    if base_query:
        queries.append(f"{claim.queries[0]} {base_query}".strip())
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        key = query.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(query.strip())
    return out


@dataclass
class InstructionGrounding:
    """Whether one clip demonstrates the advice, not merely contains its noun."""

    claim: str = ""
    label: str = ""
    checked: bool = False
    score: float = 0.0
    passed: bool = True
    detail: str = ""
    #: Which forbidden scene came closest, and by how much. Reporting only.
    top_forbidden: str = ""
    top_forbidden_margin: float = 0.0

    @property
    def required(self) -> bool:
        return bool(self.claim)

    @property
    def failed(self) -> bool:
        return self.required and self.checked and not self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_visual_claim": self.claim,
            "instruction_label": self.label,
            "instruction_grounding_score": round(self.score, 3),
            "instruction_grounding_checked": self.checked,
            "instruction_grounding_passed": self.passed,
            "instruction_grounding_detail": self.detail,
            "instruction_top_forbidden": self.top_forbidden,
            "instruction_top_forbidden_margin": round(self.top_forbidden_margin, 3),
        }


def score_from_similarities(
    claim: InstructionClaim,
    per_frame: Sequence[Sequence[float]],
    ramp: Any,
) -> InstructionGrounding:
    """Is this frame one of the scenes the advice is not about?

    Identical in shape to the entity probe, and different in what it compares:
    there, a noun against nouns; here, a stated scene against the stated
    scenes that keep arriving instead. The median over frames, so one frame
    where the camera has panned onto the window does not condemn a clip that
    shows the room.
    """

    offset = len(claim.positives)
    scores: list[float] = []
    leaders: list[tuple[float, str]] = []
    for similarities in per_frame:
        if len(similarities) <= offset:
            continue
        best_positive = max(similarities[:offset])
        forbidden = similarities[offset:]
        best_forbidden = max(forbidden)
        leaders.append((
            best_forbidden - best_positive,
            claim.forbidden[forbidden.index(best_forbidden)],
        ))
        scores.append(
            ramp(best_forbidden - best_positive, CLAIM_MARGIN_LOW, CLAIM_MARGIN_HIGH)
        )
    if not scores:
        return InstructionGrounding(claim=claim.name, label=claim.label)
    scores.sort()
    dominance = scores[len(scores) // 2]
    leaders.sort(key=lambda item: item[0], reverse=True)
    top_margin, top_name = leaders[0]
    passed = dominance < CLAIM_DOMINANCE_FAIL
    return InstructionGrounding(
        claim=claim.name,
        label=claim.label,
        checked=True,
        score=round(1.0 - dominance, 3),
        passed=passed,
        top_forbidden=top_name,
        top_forbidden_margin=top_margin,
        detail=(
            f"shows {claim.label} ({1.0 - dominance:.2f}; closest forbidden "
            f"scene {top_name!r} at {top_margin:+.3f})" if passed
            else f"does not show {claim.label}; it looks like {top_name!r} "
                 f"({1.0 - dominance:.2f}, {top_margin:+.3f})"
        ),
    )


def summarise(groundings: Iterable[Any]) -> dict[str, Any]:
    """The report's view of a whole video's final shots."""

    items = [g for g in groundings if g]
    required = [g for g in items if dict(g).get("required_visual_claim")]
    checked = [g for g in required if dict(g).get("instruction_grounding_checked")]
    failed = [g for g in checked if not dict(g).get("instruction_grounding_passed")]
    return {
        "shots": len(items),
        "making_a_claim": len(required),
        "checked": len(checked),
        "passed": len(checked) - len(failed),
        "failed": len(failed),
        "pass_percentage": (
            round(100.0 * (len(checked) - len(failed)) / len(checked), 1)
            if checked else 100.0
        ),
        "failures": [
            {
                "claim": dict(g).get("required_visual_claim"),
                "score": dict(g).get("instruction_grounding_score"),
                "detail": dict(g).get("instruction_grounding_detail"),
                "top_forbidden": dict(g).get("instruction_top_forbidden"),
            }
            for g in failed[:8]
        ],
        "by_claim": _by_claim(checked),
    }


def _by_claim(rows: Sequence[Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(dict(row).get("required_visual_claim") or "?"), []).append(
            dict(row)
        )
    out: dict[str, Any] = {}
    for name, items in sorted(grouped.items()):
        scores = sorted(float(i.get("instruction_grounding_score") or 0.0) for i in items)
        forbidden: dict[str, int] = {}
        for item in items:
            key = str(item.get("instruction_top_forbidden") or "")
            if key:
                forbidden[key] = forbidden.get(key, 0) + 1
        out[name] = {
            "shots": len(items),
            "failed": sum(1 for i in items if not i.get("instruction_grounding_passed")),
            "min_score": round(scores[0], 3),
            "median_score": round(scores[len(scores) // 2], 3),
            "closest_forbidden": dict(
                sorted(forbidden.items(), key=lambda kv: kv[1], reverse=True)[:4]
            ),
        }
    return out
