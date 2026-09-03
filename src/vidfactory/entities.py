"""The object the shot has to actually contain.

Run 25 passed every relevance gate the pipeline had:

    final_shot_visual_semantic_match_average = 0.569
    final_shot_low_relevance_percentage      = 0%

and still put colourful ribbons under "paint the trim the same colour as the
walls", potted plants under "a rug too small to reach the sofa", and doors,
people and empty rooms through the rest of the rug section.

Sentence-level CLIP similarity cannot catch that, and no threshold on it
would have. A styled living room genuinely *is* similar to a sentence about
rugs in that room: same palette, same furniture, same lighting, same domain
vocabulary. The similarity is real. The rug is simply not there.

So relevance and presence are two different questions, and this module asks
the second one. When a shot's narration is about a concrete object, that
object is **required**: the frames are compared against short prompts that say
the thing is present, against short prompts that say it is absent or that some
other object fills the frame, and the shot is grounded only if the present
reading wins by a margin. A high generic score cannot buy its way past a
missing rug.

Margins, not probabilities, for the reason :mod:`vidfactory.visual_analysis`
already gives: CLIP's classification softmax runs at a temperature of 100 and
is winner-take-all, so it turns "slightly more rug-like" into 0.99 and
"slightly less" into 0.01. The margin between the best positive and the best
competitor is small, bounded, and says what we actually want to know.

Abstract advice - balance, proportion, editing down what is on show - has no
required entity and is not gated here. Requiring an object that the sentence
never promised would reject good footage, which is the opposite of the point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .logging_utils import get_logger

log = get_logger("ENTITY")


#: How far the positive reading has to beat the *average* competing one.
#: Not the best competing one: a calibration run over sixty real Pexels clips
#: that genuinely contain their object scored them at a median of 0.049 under
#: best-versus-best, because "a close-up of furniture" and "a person standing
#: indoors" are broad prompts and a broad prompt beats a specific one on CLIP
#: similarity almost every time. That is the same generality bias
#: ``_clip_semantic`` documents and solves, and this repeated it.
ENTITY_MARGIN_LOW = -0.02
ENTITY_MARGIN_HIGH = 0.06

#: The score a shot needs to count as showing its object. Set from the
#: calibration run rather than by analogy - see ``vidfactory entity-check``.
ENTITY_PRESENCE_PASS = 0.5


@dataclass(frozen=True)
class VisualEntity:
    """One object a piece of advice can require the camera to be pointed at.

    ``triggers`` decide whether the entity is required at all, and are matched
    against the shot's own narration chunk rather than the whole section, so a
    passing mention of the sofa in rug advice does not start demanding sofas.

    ``positives`` and ``competitors`` are what MobileCLIP actually scores. Both
    are short: a long prompt drifts towards describing a whole scene, and the
    question here is only whether one object is in the picture.

    ``queries`` are what the repair pass searches with when the object is
    missing - phrased around the object rather than around the advice, because
    the advice is what found the plants in the first place.
    """

    name: str
    labels: tuple[str, ...]
    triggers: tuple[str, ...]
    positives: tuple[str, ...]
    competitors: tuple[str, ...]
    queries: tuple[str, ...]


#: Ordered by specificity: "wall art" is art before it is a wall, and a
#: "mirror" hung on a wall is a mirror before it is either.
ENTITIES: tuple[VisualEntity, ...] = (
    VisualEntity(
        name="rug",
        labels=("rug", "carpet", "area rug"),
        triggers=("rug", "rugs", "area rug", "carpet", "runner"),
        positives=(
            "an area rug on the floor",
            "a carpet on a living room floor",
            "a sofa standing on a rug",
            "a large rug under a coffee table",
        ),
        competitors=(
            "a floor with no rug",
            "indoor potted plants",
            "a plain bare floor",
            "a close-up of furniture",
            "a person standing indoors",
            "a door and a blank wall",
        ),
        queries=(
            "properly sized area rug under sofa",
            "large rug front sofa legs",
            "small rug under coffee table mistake",
            "living room area rug covering floor",
        ),
    ),
    VisualEntity(
        name="window_dressing",
        labels=("curtains", "drapes", "window treatment"),
        triggers=(
            "curtain", "curtains", "drape", "drapes", "blind", "blinds",
            "curtain rod", "valance", "sheer", "window treatment",
        ),
        positives=(
            "curtains hanging beside a window",
            "long drapes on a curtain rod",
            "a window with fabric window treatments",
        ),
        competitors=(
            "a bare window with no curtains",
            "a blank wall",
            "indoor potted plants",
            "a close-up of furniture",
            "a person standing indoors",
        ),
        queries=(
            "floor length curtains hung high above window",
            "wide curtain rod drapes beside window",
            "sheer curtains daylight living room",
        ),
    ),
    VisualEntity(
        name="wall_finish",
        labels=("wall", "trim", "molding", "painting the wall"),
        triggers=(
            "paint", "painted", "painting", "wall color", "wall colour",
            "trim", "skirting", "moulding", "molding", "baseboard",
            "wallpaper", "panelling", "paneling", "the walls", "wall",
        ),
        positives=(
            "a painted interior wall",
            "painted trim and moulding on a wall",
            "a person painting a wall with a roller",
            "a wall and its skirting board in one colour",
        ),
        competitors=(
            "colourful clothing and ribbons",
            "indoor potted plants",
            "a close-up of furniture",
            "an outdoor street scene",
            "a person at a desk",
        ),
        queries=(
            "painted wall trim same color as wall",
            "interior wall and baseboard painted one color",
            "person painting interior wall roller",
        ),
    ),
    VisualEntity(
        name="wall_art",
        labels=("wall art", "painting", "framed art"),
        triggers=(
            "art", "artwork", "print", "prints", "poster", "canvas",
            "gallery wall", "picture frame", "framed", "wall art", "pictures",
        ),
        positives=(
            "framed art hanging on a wall",
            "a gallery wall of pictures",
            "a large painting above a sofa",
        ),
        competitors=(
            "a blank wall with nothing on it",
            "curtains beside a window",
            "indoor potted plants",
            "a close-up of furniture",
            "a person standing indoors",
        ),
        queries=(
            "framed art hung at eye level above sofa",
            "large canvas artwork on living room wall",
            "gallery wall picture frames living room",
        ),
    ),
    VisualEntity(
        name="mirror",
        labels=("mirror", "reflection"),
        triggers=("mirror", "mirrors", "mirrored", "reflection", "reflect"),
        positives=(
            "a large mirror on a wall",
            "a mirror reflecting a room",
            "a framed mirror in a living room",
        ),
        competitors=(
            "a wall with no mirror",
            "framed art on a wall",
            "a window with curtains",
            "indoor potted plants",
            "a close-up of furniture",
        ),
        queries=(
            "large mirror opposite window living room",
            "oversized wall mirror reflecting daylight",
            "framed mirror above console table",
        ),
    ),
    VisualEntity(
        name="seating",
        labels=("sofa", "couch", "room layout"),
        triggers=(
            "sofa", "couch", "sectional", "loveseat", "armchair", "seating",
            "chair", "chairs", "ottoman",
        ),
        positives=(
            "a sofa in a living room",
            "a couch and armchairs arranged in a room",
            "a living room seating layout",
        ),
        competitors=(
            "an empty room with no furniture",
            "a close-up of a cushion",
            "indoor potted plants",
            "a kitchen counter",
            "an outdoor street scene",
        ),
        queries=(
            "sofa pulled away from wall living room layout",
            "living room sofa and armchairs arrangement",
            "small living room sofa placement",
        ),
    ),
    VisualEntity(
        name="window",
        labels=("window", "daylight", "glass"),
        triggers=("window", "windows", "daylight", "natural light", "the glass", "sunlight"),
        positives=(
            "a window letting daylight into a room",
            "sunlight coming through a glass window",
            "a bright room with a large window",
        ),
        competitors=(
            "a room with no window",
            "a dark interior at night",
            "a close-up of furniture",
            "indoor potted plants",
            "an outdoor street scene",
        ),
        queries=(
            "daylight through large living room window",
            "bright room natural light from window",
            "uncovered window daylight interior",
        ),
    ),
    VisualEntity(
        name="lighting",
        labels=("lamp", "light fixture", "illuminated wall"),
        triggers=(
            "lamp", "lamps", "sconce", "pendant", "chandelier", "bulb",
            "light fixture", "lampshade", "floor lamp", "table lamp",
            "lighting", "light source", "light sources",
        ),
        positives=(
            "a lit floor lamp in a room",
            "a table lamp switched on",
            "a wall sconce lighting a wall",
            "a pendant light hanging from a ceiling",
        ),
        competitors=(
            "a room with no lamp",
            "daylight through a window",
            "a close-up of furniture",
            "indoor potted plants",
            "a person standing indoors",
        ),
        queries=(
            "floor lamp lit corner living room",
            "table lamp switched on side table",
            "wall sconce washing light up a wall",
        ),
    ),
    VisualEntity(
        name="greenery",
        labels=("plant",),
        triggers=("plant", "plants", "greenery", "foliage", "tree"),
        positives=(
            "a potted plant indoors",
            "a tall houseplant in a corner",
            "green foliage in a living room",
        ),
        competitors=(
            "a room with no plants",
            "a close-up of furniture",
            "a blank wall",
            "an outdoor garden",
        ),
        queries=(
            "tall potted plant living room corner",
            "indoor houseplant beside sofa",
        ),
    ),
    VisualEntity(
        name="storage",
        labels=("shelving", "cabinet", "storage"),
        triggers=(
            "shelf", "shelves", "shelving", "bookcase", "cabinet", "cupboard",
            "wardrobe", "storage", "basket", "baskets", "drawer", "drawers",
        ),
        positives=(
            "shelves on a wall",
            "a bookcase in a living room",
            "a closed storage cabinet",
        ),
        competitors=(
            "a blank wall with no shelves",
            "a close-up of furniture",
            "indoor potted plants",
            "a person standing indoors",
        ),
        queries=(
            "tall bookcase shelving living room wall",
            "closed storage cabinet living room",
            "baskets storing clutter living room",
        ),
    ),
)

BY_NAME: dict[str, VisualEntity] = {e.name: e for e in ENTITIES}


def _normalise(text: str) -> str:
    return f" {re.sub(r'[^a-z0-9 ]+', ' ', str(text or '').lower())} "


def _hits(entity: VisualEntity, haystack: str) -> int:
    return sum(
        1 for word in entity.triggers
        if re.search(rf"\b{re.escape(word)}\b", haystack)
    )


def required_entity(text: str) -> VisualEntity | None:
    """The object this shot has to show, or ``None`` when it is abstract.

    Only one object is required. Rug advice mentions the sofa the rug has to
    reach, and demanding both would reject a perfectly good photograph of a
    rug under a coffee table.

    The subject is the object named *first*, not the one named most often.
    "A rug too small to reach the sofa leaves the seating floating" names
    seating twice and the rug once, and it is advice about rugs - the sofa is
    the landmark the rug is measured against. Count breaks ties, and where
    even that ties, :data:`ENTITIES` order does: wall art before wall.
    """

    haystack = _normalise(text)
    if not haystack.strip():
        return None

    scored: list[tuple[int, int, VisualEntity]] = []
    for entity in ENTITIES:
        count = _hits(entity, haystack)
        if not count:
            continue
        first = min(
            (m.start() for word in entity.triggers
             if (m := re.search(rf"\b{re.escape(word)}\b", haystack))),
            default=len(haystack),
        )
        scored.append((first, -count, entity))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]))
    return scored[0][2]


def required_labels(text: str) -> list[str]:
    """What the report calls the requirement, e.g. ``["rug", "carpet", ...]``."""

    entity = required_entity(text)
    return list(entity.labels) if entity else []


def repair_queries(text: str, base_query: str = "") -> list[str]:
    """Searches phrased around the missing object rather than the advice.

    The advice is what found the plants: "a rug too small to reach the sofa"
    is a sentence about proportion, and a stock library will happily answer it
    with a beautifully proportioned room. Naming the object is what changes
    the result set.
    """

    entity = required_entity(text)
    if entity is None:
        return [q for q in (base_query,) if q]
    queries = list(entity.queries)
    if base_query:
        queries.append(f"{entity.labels[0]} {base_query}".strip())
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        key = query.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(query.strip())
    return out


@dataclass
class EntityGrounding:
    """Whether one clip actually contains the object its narration is about."""

    entity: str = ""
    labels: tuple[str, ...] = ()
    checked: bool = False
    score: float = 0.0
    passed: bool = True
    detail: str = ""

    @property
    def required(self) -> bool:
        return bool(self.entity)

    @property
    def failed(self) -> bool:
        """A measured absence. An unchecked shot is not a failure."""

        return self.required and self.checked and not self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_visual_entities": list(self.labels),
            "entity": self.entity,
            "entity_presence_score": round(self.score, 3),
            "entity_grounding_checked": self.checked,
            "entity_grounding_passed": self.passed,
            "entity_grounding_detail": self.detail,
        }


def grounding_prompts(entity: VisualEntity) -> tuple[list[str], int]:
    """(every prompt to encode, where the competitors start)."""

    return [*entity.positives, *entity.competitors], len(entity.positives)


def score_from_similarities(
    entity: VisualEntity,
    per_frame: Sequence[Sequence[float]],
    ramp: Any,
) -> EntityGrounding:
    """Where the positive reading lands among all the readings, per frame.

    The first version of this took the best positive against the *best*
    competitor, and a calibration run said so plainly: sixty real clips
    containing their object scored a median of 0.049, while clips of something
    else scored 0.373. Anti-correlated, not merely mis-thresholded.

    The cause is the generality bias :func:`_clip_semantic` already documents.
    "a close-up of furniture" and "a person standing indoors" are broad, "a lit
    floor lamp in a room" is specific, and CLIP scores the broad prompt higher
    against almost any photograph - so a maximum taken over five broad
    competitors beats a maximum taken over four specific positives whether or
    not the lamp is there. Worse, it is not even wrong about the picture: a
    clip of a rug under a sofa genuinely *is* a close-up of furniture.

    So this asks the scale-free question instead, the same two signals that
    module settled on: where the best positive sits in the range of all the
    similarities, and how far it beats the *average* competitor rather than
    the luckiest one.

    The median over frames, for the reason the pixel flags use one: a single
    frame where the camera has panned off the rug should not condemn a clip
    that shows it, and a single lucky frame should not rescue one that does not.
    """

    offset = len(entity.positives)
    margins: list[float] = []
    for similarities in per_frame:
        if len(similarities) <= offset:
            continue
        best_positive = max(similarities[:offset])
        competitors = similarities[offset:]
        low, high = min(similarities), max(similarities)
        spread = high - low
        position = (best_positive - low) / spread if spread > 1e-6 else 0.5
        margin = best_positive - (sum(competitors) / len(competitors))
        margins.append(
            0.65 * position
            + 0.35 * ramp(margin, ENTITY_MARGIN_LOW, ENTITY_MARGIN_HIGH)
        )
    if not margins:
        return EntityGrounding(entity=entity.name, labels=entity.labels)
    margins.sort()
    score = margins[len(margins) // 2]
    passed = score >= ENTITY_PRESENCE_PASS
    return EntityGrounding(
        entity=entity.name,
        labels=entity.labels,
        checked=True,
        score=round(score, 3),
        passed=passed,
        detail=(
            f"{entity.labels[0]} present ({score:.2f})" if passed
            else f"no {entity.labels[0]} visible ({score:.2f})"
        ),
    )


def summarise(groundings: Iterable[Any]) -> dict[str, Any]:
    """The report's view of a whole video's final shots."""

    items = [g for g in groundings if g]
    required = [g for g in items if dict(g).get("entity")]
    checked = [g for g in required if dict(g).get("entity_grounding_checked")]
    failed = [g for g in checked if not dict(g).get("entity_grounding_passed")]
    return {
        "shots": len(items),
        "requiring_an_entity": len(required),
        "checked": len(checked),
        "passed": len(checked) - len(failed),
        "failed": len(failed),
        "pass_percentage": (
            round(100.0 * (len(checked) - len(failed)) / len(checked), 1)
            if checked else 100.0
        ),
        "failures": [
            {
                "entity": dict(g).get("entity"),
                "score": dict(g).get("entity_presence_score"),
                "detail": dict(g).get("entity_grounding_detail"),
            }
            for g in failed[:8]
        ],
    }


def entities_in(text: str) -> set[str]:
    """Every entity the text names, whether or not it is the subject.

    Used to read an enumeration - "a plant, a floor lamp, a mirror or a
    chair" - as the set of options it offers, where
    :func:`required_entity` would pick only the first.
    """

    haystack = _normalise(text)
    return {e.name for e in ENTITIES if _hits(e, haystack)}
