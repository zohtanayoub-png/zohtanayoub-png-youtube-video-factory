"""The food a reel beat has to actually show.

The long-form side learned that similarity is not presence: a styled living
room matches a sentence about the rug in it whether or not the rug is there.
A reel has the same disease with a sharper symptom. The last render narrated
"la manzana con piel conserva la fibra" over a close-up of an **orange**, at a
semantic match high enough to be selected, because a bowl of citrus on a
wooden table genuinely is similar to a sentence about fruit on a table.

So this is `entities.py` pointed at food. The machinery is imported rather
than copied - :class:`VisualEntity`, :func:`grounding_prompts` and
:func:`score_from_similarities` are all neutral, and the only thing that was
long-form about them was the registry - and what is new here is the registry,
the Spanish triggers, and one rule the interiors never needed:

**a beat that names one food requires that food; a beat that names several
requires none.** "Fresas, frambuesas, kiwi, manzana con piel y aguacate" is
the answer beat, and demanding a single fruit of it would reject the mixed
bowl that is exactly the right picture. "Las fresas suelen aportar menos
carbohidratos por racion" names one, and a bowl of raspberries is wrong.

The competitors are what a stock search actually returns instead, which for
food is the near neighbour rather than the unrelated object: search for
strawberries and you get raspberries, search for kiwi and you get lime. That
is a much sharper question than the interiors ever asked - a photograph
contains a wall and a floor and a sofa at once, but a fruit close-up is of one
fruit - and it is why the thresholds here are their own.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence

from ..entities import (
    EntityGrounding,
    VisualEntity,
    grounding_prompts,
    score_from_similarities,
)
from ..logging_utils import get_logger

log = get_logger("REELFOOD")

#: The margin band, and the cut. Deliberately *not* the interiors' numbers.
#:
#: These are placeholders until ``vidfactory reel-entity-check`` has scored
#: real footage: see the calibration note in CLAUDE.md. The shape is the same
#: as `entities.ENTITY_*` - how far the best competitor has to beat the best
#: description of the food before the frame counts as being about the
#: competitor - and the reason the band is tighter is that one fruit in
#: close-up is a much more separable question than one object in a room.
FOOD_MARGIN_LOW = 0.0
FOOD_MARGIN_HIGH = 0.05

#: Above this share of frames dominated by a competitor, the shot is wrong.
FOOD_DOMINANCE_FAIL = 0.50


def _food(
    name: str,
    labels: Sequence[str],
    triggers: Sequence[str],
    positives: Sequence[str],
    competitors: Sequence[str],
    queries: Sequence[str],
) -> VisualEntity:
    return VisualEntity(
        name=name,
        labels=tuple(labels),
        triggers=tuple(triggers),
        positives=tuple(positives),
        competitors=tuple(competitors),
        queries=tuple(queries),
    )


#: Every food a beat can be *about*. Positives and competitors are English
#: because that is what CLIP was trained on and what the providers are
#: searched in; only the triggers are Spanish, because that is what the
#: narration is written in.
FOODS: tuple[VisualEntity, ...] = (
    _food(
        "fresas", ["strawberries"],
        ["fresa", "fresas"],
        ["fresh strawberries", "a bowl of red strawberries",
         "whole strawberries close up"],
        ["raspberries", "cherries", "blueberries", "a tomato",
         "mixed berries with no strawberries"],
        ["fresh strawberries in a white bowl", "whole strawberries close up",
         "ripe red strawberries on a table", "sliced strawberries on a plate"],
    ),
    _food(
        "frambuesas", ["raspberries"],
        ["frambuesa", "frambuesas"],
        ["fresh raspberries", "a bowl of raspberries",
         "raspberries close up"],
        ["strawberries", "blackberries", "cherries", "redcurrants",
         "mixed berries with no raspberries"],
        ["fresh raspberries close up bowl", "a bowl of ripe raspberries",
         "raspberries on a wooden table", "raspberries in a punnet"],
    ),
    _food(
        "kiwi", ["kiwi fruit"],
        ["kiwi", "kiwis"],
        ["sliced kiwi fruit", "kiwi fruit cut in half",
         "green kiwi slices on a plate"],
        ["a lime", "a green apple", "an avocado", "a cucumber",
         "a slice of melon"],
        ["sliced kiwi fruit on a plate", "kiwi fruit cut in half close up",
         "fresh kiwi fruit on a table", "peeled kiwi slices"],
    ),
    _food(
        "manzana", ["an apple"],
        ["manzana", "manzanas"],
        ["a red apple", "a whole apple with skin", "sliced apple on a board",
         "a green apple"],
        # The orange is first because the orange is what actually shipped.
        ["an orange", "a peach", "a pear", "a lemon", "a tomato",
         "a glass of orange juice"],
        ["whole red apple with skin on a wooden table", "red apple close up",
         "sliced apple with skin on a board", "fresh apples on a table"],
    ),
    _food(
        "aguacate", ["an avocado"],
        ["aguacate", "aguacates"],
        ["a halved avocado", "avocado cut in half with the stone",
         "sliced avocado on a board"],
        ["a kiwi fruit", "a lime", "a green apple", "a pear",
         "guacamole dip"],
        ["halved avocado on a wooden board", "avocado cut in half close up",
         "sliced ripe avocado on a plate", "fresh avocados on a table"],
    ),
    _food(
        "platano", ["a banana"],
        ["platano", "platanos", "banana", "bananas"],
        ["ripe yellow bananas", "a bunch of bananas", "a peeled banana"],
        ["a mango", "a lemon", "corn", "a papaya"],
        ["ripe yellow bananas on a table", "a bunch of ripe bananas",
         "peeled banana close up", "bananas in a fruit bowl"],
    ),
    _food(
        "uvas", ["grapes"],
        ["uva", "uvas"],
        ["a bunch of green grapes", "red grapes on the vine",
         "grapes close up"],
        ["cherries", "blueberries", "olives", "currants"],
        ["bunch of green grapes close up", "red grapes on a wooden table",
         "fresh grapes in a bowl", "a bunch of grapes on the vine"],
    ),
    _food(
        "datiles", ["dates"],
        ["datil", "datiles"],
        ["dried dates in a bowl", "medjool dates close up",
         "whole dried dates"],
        ["raisins", "figs", "prunes", "dried apricots", "chocolate"],
        ["dried dates in a bowl", "medjool dates close up",
         "whole dates on a plate", "dried dates on a wooden board"],
    ),
    _food(
        "naranja", ["an orange"],
        ["naranja", "naranjas"],
        ["a whole orange", "orange segments on a table",
         "peeled orange close up"],
        ["a lemon", "a grapefruit", "a tangerine", "an apple",
         "a glass of orange juice"],
        ["whole oranges and orange segments on a table", "an orange cut in half",
         "fresh oranges on a wooden table", "peeled orange segments"],
    ),
    _food(
        "zumo", ["a glass of juice"],
        ["zumo", "zumos", "exprimir", "exprimirla"],
        ["a glass of orange juice", "orange juice being poured into a glass",
         "a tall glass of fruit juice"],
        ["a whole orange", "a glass of milk", "a smoothie", "a glass of water",
         "a bowl of fruit"],
        ["glass of fresh orange juice on a table", "orange juice poured into a glass",
         "a glass of juice at breakfast", "carton of orange juice and a glass"],
    ),
    _food(
        "yogur", ["plain yogurt"],
        ["yogur", "yogures", "requeson"],
        ["a bowl of plain white yogurt", "greek yogurt in a bowl",
         "yogurt with a spoon"],
        ["a glass of milk", "whipped cream", "ice cream", "cottage cheese",
         "a bowl of soup"],
        ["plain yogurt in a glass bowl", "greek yogurt in a white bowl",
         "a bowl of natural yogurt with a spoon", "yogurt pot open on a table"],
    ),
    _food(
        "avena", ["oats"],
        ["avena", "copos de avena"],
        ["a bowl of oatmeal", "rolled oats in a bowl", "porridge with berries"],
        ["breakfast cereal flakes", "rice", "granola", "muesli", "couscous"],
        ["oatmeal bowl with berries and cinnamon", "rolled oats in a wooden bowl",
         "porridge in a bowl close up", "a bowl of oats and milk"],
    ),
    _food(
        "huevo", ["an egg"],
        ["huevo", "huevos"],
        ["boiled eggs cut in half", "scrambled eggs on a plate",
         "a fried egg"],
        ["cheese", "a potato", "an onion", "tofu", "a mushroom"],
        ["boiled eggs cut in half on a plate", "scrambled eggs with vegetables",
         "a fried egg on a plate", "eggs in a bowl"],
    ),
    _food(
        "nueces", ["walnuts"],
        ["nuez", "nueces"],
        ["a handful of walnuts", "walnuts in a bowl", "shelled walnuts close up"],
        ["almonds", "peanuts", "hazelnuts", "cashews", "pecans"],
        ["handful of walnuts in a bowl", "shelled walnuts close up",
         "walnuts on a wooden table", "a bowl of walnut halves"],
    ),
    _food(
        "granola", ["granola"],
        ["granola"],
        ["a bowl of granola", "granola clusters close up",
         "granola with milk in a bowl"],
        ["rolled oats", "breakfast cereal flakes", "muesli", "nuts in a bowl"],
        ["granola in a bowl with milk", "granola clusters close up",
         "a bowl of granola and yogurt", "homemade granola on a tray"],
    ),
    _food(
        "bolleria", ["pastries"],
        ["bolleria"],
        ["croissants and pastries on a plate", "a chocolate croissant",
         "sweet pastries in a bakery"],
        ["bread rolls", "a sandwich", "a cake slice", "biscuits"],
        ["croissants and pastries on a plate", "a croissant close up",
         "sweet pastries on a wooden board", "bakery pastries display"],
    ),
    _food(
        "pan_integral", ["wholegrain bread"],
        ["pan integral", "harina integral"],
        ["a loaf of wholegrain bread", "sliced brown bread",
         "wholemeal bread on a board"],
        ["white bread", "a croissant", "a cake", "crackers"],
        ["whole grain bread loaf on a board", "sliced wholemeal bread",
         "brown bread on a wooden table", "wholegrain bread slices close up"],
    ),
    _food(
        "hummus", ["hummus"],
        ["hummus"],
        ["hummus with carrot sticks", "a bowl of hummus",
         "hummus dip with vegetables"],
        ["guacamole", "yogurt dip", "peanut butter", "soup"],
        ["hummus with carrot sticks on a plate", "a bowl of hummus close up",
         "hummus and raw vegetables", "hummus dip with crudites"],
    ),
)

BY_NAME: dict[str, VisualEntity] = {f.name: f for f in FOODS}

#: Which food an item is *about*, by the item's own key.
#:
#: Keyed rather than parsed, because the item already knows: "Cambiar la fruta
#: entera por zumo le quita la fibra" names both the fruit and the juice, and
#: the subject is the juice. Items missing from this map require nothing,
#: which is the correct answer for advice about a label, a scale or a
#: portion - demanding an object a sentence never promised rejects good
#: footage, exactly as it does on the long-form side.
ITEM_FOOD: dict[str, str] = {
    "fresas": "fresas",
    "frambuesas": "frambuesas",
    "kiwi": "kiwi",
    "manzana": "manzana",
    "aguacate": "aguacate",
    "platano": "platano",
    "uvas": "uvas",
    "datiles": "datiles",
    "naranja": "naranja",
    "zumo": "zumo",
    "zumo_desayuno": "zumo",
    "zumo_por_fruta": "zumo",
    "quitar_piel": "manzana",
    "yogur_nat": "yogur",
    "yogur_natural": "yogur",
    "yogur_nueces": "yogur",
    "requeson_kiwi": "yogur",
    "avena": "avena",
    "huevo_duro": "huevo",
    "huevos_verduras": "huevo",
    "nueces": "nueces",
    "granola": "granola",
    "bolleria": "bolleria",
    "integral": "pan_integral",
    "hummus_zanahoria": "hummus",
    "manzana_crema": "manzana",
    "tostada_aguacate": "aguacate",
}


def _fold(text: str) -> str:
    flat = unicodedata.normalize("NFKD", str(text or "").lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", flat).strip() + " "


def foods_named(text: str) -> list[VisualEntity]:
    """Every food this sentence names, most specific first."""

    haystack = _fold(text)
    found: list[VisualEntity] = []
    for food in FOODS:
        if any(f" {_fold(t).strip()} " in haystack for t in food.triggers):
            found.append(food)
    return found


def required_food(text: str, item_key: str = "") -> VisualEntity | None:
    """The one food this beat has to show, or ``None``.

    The item's key wins when it has one, because the item knows its own
    subject and a sentence does not: "cambiar la fruta entera por zumo" names
    two foods and is about the second.

    Falling back to the sentence, the rule is **exactly one**. A beat naming
    several foods is a list, and the right picture for a list is the mixed
    bowl that naming any single one of them would reject.
    """

    key = str(item_key or "").strip()
    if key in ITEM_FOOD:
        return BY_NAME[ITEM_FOOD[key]]
    named = foods_named(text)
    return named[0] if len(named) == 1 else None


def required_food_for(beat: Any) -> VisualEntity | None:
    """The food a script beat requires, if any.

    Only item beats. The hook, the answer, the retention line, the takeaway
    and the CTA are about the reel rather than about a food - the answer names
    five of them - and holding them to one fruit would reject the establishing
    shot that belongs there.
    """

    if str(getattr(beat, "kind", "")) != "item":
        return None
    return required_food(
        str(getattr(beat, "text", "")), str(getattr(beat, "item_key", ""))
    )


def score_food(entity: VisualEntity, per_frame: Sequence[Sequence[float]], ramp: Any):
    """The same dominance question the interiors ask, at the food thresholds.

    Kept for comparison and **not** used: the first calibration measured it at
    chance. See :func:`identify_food`, and the note in CLAUDE.md.
    """

    return score_from_similarities(
        entity,
        per_frame,
        ramp,
        margin_low=FOOD_MARGIN_LOW,
        margin_high=FOOD_MARGIN_HIGH,
        dominance_fail=FOOD_DOMINANCE_FAIL,
    )


#: What share of frames must name the right food for the shot to be about it.
#:
#: Placeholder until the identification probe has been swept. The dominance
#: probe above was measured first and came back at chance - kept% + rejected%
#: summed to ~100 at every cut, and manzana was *inverted*, real apple footage
#: at a median of 0.131 against orange footage at 0.508.
FOOD_IDENTIFY_PASS = 0.60


def identify_food(
    entity: VisualEntity, per_frame: Sequence[Sequence[float]], ramp: Any = None
) -> EntityGrounding:
    """Which food does this frame look most like?

    A different question from the interiors', because food is a different
    kind of subject. "Does this room contain a wall" is true of every room, so
    the only answerable question there was displacement - how far something
    else beats the wall. But a fruit close-up is *of one fruit*: apple, orange
    and pear are mutually exclusive in a way a wall and a sofa are not, so the
    answerable question is plain identification.

    So this ranks every prompt - the food's own descriptions and the foods it
    is confused with - and asks which came first. The score is the share of
    frames where the right food won, and there is no margin band: a frame that
    looks marginally more like an orange than an apple is a frame of an
    orange.
    """

    positives = len(entity.positives)
    wins = 0
    counted = 0
    losers: dict[str, int] = {}
    for similarities in per_frame:
        if len(similarities) <= positives:
            continue
        counted += 1
        best = max(range(len(similarities)), key=lambda i: similarities[i])
        if best < positives:
            wins += 1
        else:
            name = entity.competitors[best - positives]
            losers[name] = losers.get(name, 0) + 1
    if not counted:
        return EntityGrounding(entity=entity.name, labels=entity.labels)
    share = wins / counted
    top = max(losers.items(), key=lambda kv: kv[1])[0] if losers else ""
    passed = share >= FOOD_IDENTIFY_PASS
    return EntityGrounding(
        entity=entity.name,
        labels=entity.labels,
        checked=True,
        score=round(share, 3),
        passed=passed,
        top_distractor=top,
        top_distractor_margin=round(1.0 - share, 3),
        detail=(
            f"{entity.labels[0]} named in {wins}/{counted} frames" if passed
            else f"only {wins}/{counted} frames look like {entity.labels[0]}"
                 + (f"; {top} won the rest" if top else "")
        ),
    )


def food_prompts(entity: VisualEntity) -> tuple[list[str], int]:
    return grounding_prompts(entity)


def repair_queries(entity: VisualEntity, spent: Sequence[str] = ()) -> list[str]:
    """Explicit object searches for a food the footage failed to show.

    Phrased around the food and nothing else. The beat's own query is what
    returned the orange, so repeating it with more pages would keep returning
    the orange.
    """

    used = {str(q).strip().lower() for q in spent}
    return [q for q in entity.queries if q.strip().lower() not in used]
