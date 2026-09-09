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
from dataclasses import dataclass
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
        # Arrangement rather than a close-up of one berry. Measured twice on
        # two independent fresh four-berry sets: the four-way confusion
        # accuracy goes 0.583 -> 0.667 and 0.750 -> 0.792, strawberry
        # precision reaches 1.000, and raspberry recall 0.500 -> 0.667. The
        # centre crop that looked promising on the development pile is *not*
        # here: it lost on both fresh sets (0.667 -> 0.542, 0.750 -> 0.542).
        #
        # These name punnets and bowls where the context prompts may not,
        # and the difference is what each probe is for: an entity positive
        # describes what the food looks like in quantity, which is most of
        # what tells a raspberry pile from a strawberry pile. Context asks
        # whether the food is the subject, and there the crockery is
        # furniture.
        ["a punnet of strawberries stacked in rows",
         "many red strawberries filling a bowl",
         "strawberries piled on a wooden table"],
        ["raspberries", "cherries", "blueberries", "a tomato",
         "mixed berries with no strawberries"],
        ["fresh strawberries in a white bowl", "whole strawberries close up",
         "ripe red strawberries on a table", "sliced strawberries on a plate"],
    ),
    _food(
        "frambuesas", ["raspberries"],
        ["frambuesa", "frambuesas"],
        ["a punnet of raspberries stacked in rows",
         "many small raspberries filling a bowl",
         "raspberries piled on a wooden table"],
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
        # Every positive used to describe a *cut*, which is how a whole
        # avocado - dark bumpy skin, no green flesh anywhere - came to be
        # rejected by the layer under the state probe. Naming the whole fruit
        # did not by itself buy the whole-avocado clips back (run 34153962478:
        # 4 of 6 either way), but adding the pile alongside it dominates the
        # shipped wording outright - the same 10 of 12 valid clips kept, and
        # false positives on pears and limes halved from 2 of 6 to 1 of 6.
        ["a whole avocado with dark bumpy skin",
         "a halved avocado with the stone", "sliced green avocado",
         "a pile of avocados"],
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
#: Read off the sweep, on the validated ViT-L/14, over 28 clips found by
#: searching for the food and 28 found by searching for the food that turns
#: up instead:
#:
#:     cut    kept of correct    rejected of wrong
#:     0.20     23/28 (82.1%)      26/28 ( 92.9%)
#:     0.40     23/28 (82.1%)      28/28 (100.0%)
#:     0.50     23/28 (82.1%)      28/28 (100.0%)
#:     0.60     23/28 (82.1%)      28/28 (100.0%)
#:     0.70     20/28 (71.4%)      28/28 (100.0%)
#:
#: 0.5 is the middle of the plateau: everything from 0.4 to 0.6 catches every
#: wrong-food clip at the same cost, and 0.7 starts charging for nothing.
#: Per food, apple against orange - the failure that started this - separates
#: perfectly, 1.0 against 0.0, as do kiwi and avocado; strawberries run
#: 0.834 against 0.0.
#:
#: **Raspberries do not identify themselves at all** (0.0 against 0.0) and are
#: the whole of the 5-in-28 loss. Recorded rather than tuned away: dropping
#: "strawberries" from the raspberry competitors would buy the number back and
#: would be exactly the "lower the threshold until it passes" this is meant to
#: avoid. What it costs is that a raspberry beat is repaired three times and
#: then reported, which is the right failure to have.
FOOD_IDENTIFY_PASS = 0.5


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




# ---------------------------------------------------------------------------
# Entity + state + context, because the entity alone was not enough
# ---------------------------------------------------------------------------
#
# ``identify_food`` fixed the failure it was written for: the apple beat no
# longer settles for an orange, and over three renders it never did again.
# What those renders then shipped is the next failure along, and it is the
# same failure the long-form side hit between ``entities.py`` and
# ``instructions.py``: a frame can contain the right noun and still be the
# wrong picture.
#
#     "la manzana con piel conserva la fibra"  over an apple **cake**
#     "la manzana con piel conserva la fibra"  over a **peeled** apple
#     "las fresas suelen aportar menos ..."    over a **dog**, with
#                                              strawberries somewhere behind it
#     "el kiwi ..."                            over a **coconut**, kiwi beside
#
# Every one of those scores ``manzana = 1.00``. They are apples. A cake made
# of apples is more like "a red apple" than like "an orange", so the
# identification probe is answering its own question correctly and the
# question is too small. An apple beat needs an apple **that is raw and has
# its skin on**, presented **as food**, and **not standing behind a dog**.
#
# So a requirement here has the four parts the failures have, and they are
# scored as a conjunction rather than as a sum. A strong entity score may not
# buy a failed state: that is the whole point of the layer, and an average
# would hand the cake exactly the compensation it needs.

#: The animals and objects that turned up owning a food frame. Shared,
#: because a dog in front of the strawberries is a dog in front of anything.
#: Deliberately **not** "a person's hands" or "a person holding fruit": a
#: hand holding an apple is a normal, good food shot, and half of the stock
#: footage in this niche has one in it. What is wrong is a face where the
#: food should be.
COMMON_DOMINANT_DISTRACTORS: tuple[str, ...] = (
    "a dog",
    "a cat",
    "a close-up of a person's face with no food visible",
)

#: What a food shot must not be *about*, whichever food it is. Packaging and
#: branding rather than the thing itself: the brief's "avocado-branded
#: product where the fruit is not actually visible".
#:
#: The positives beside these describe the **food** and never the crockery.
#: "In a bowl as the main subject" and "on a kitchen table" rejected
#: strawberries on linen, raspberries in a glass jar and apples in market
#: boxes in run 34154410206 - valid footage with the wrong furniture - and a
#: prompt naming a container is a prompt about that container. Presentation
#: is not something a beat about fruit gets to require.
#: What the *ranking* score compares a beat's picture against.
#:
#: Not the grounding gate - that is the four-probe conjunction below and it
#: does not change. This is ``visual_semantic_match``, the number that orders
#: the shortlist, and it was measured at **0.217** across a whole reel with
#: nineteen of twenty-three clips called low relevance (run 34165114277). The
#: reason is that the analyzer's own alternatives describe *rooms* - "a
#: kitchen counter", "a bedroom with a made bed", "a close-up of a potted
#: plant" - and a macro shot of raspberries on a board genuinely does look
#: like a kitchen counter. The fruit prompt was losing to furniture.
#:
#: These are the alternatives a *food* search returns instead, taken from the
#: failures already on record: the dessert made of the fruit, the drink made
#: of it, the packaged version, the person holding it, the field it grew in.
#: They are meant to be competitive - a straw-man list would put every clip at
#: the top of the range and measure nothing.
FOOD_SEMANTIC_DISTRACTORS: tuple[str, ...] = (
    "a plate of cooked food",
    "a cake or a dessert with cream",
    "a drink in a glass",
    "a person in a kitchen",
    "packaged food on a supermarket shelf",
    "a green salad",
    "a close-up of a person's hands",
    "a garden or a field of crops",
    "an empty table or worktop",
)


WRONG_CONTEXT: tuple[str, ...] = (
    "a branded supermarket product in printed packaging",
    "a printed logo or an advertisement",
    "a supermarket shelf full of packaged goods",
)


@dataclass(frozen=True)
class VisualRequirement:
    """Everything one beat's footage has to satisfy, not just the noun.

    The fields are prompts as well as requirements, and that is deliberate:
    a requirement written as a sentence CLIP can score is a requirement a
    reviewer can also read, and keeping two parallel lists in step is how
    they stop being in step.

    ``required_attributes`` / ``forbidden_attributes`` are the **state**:
    raw against cooked, whole against peeled, the fruit against the dessert
    made of it. ``context_requirements`` is the kind of scene, scored against
    :data:`WRONG_CONTEXT`. ``forbidden_dominant_entities`` are the things
    that turned up owning the frame while the food sat in the background.

    Empty lists are not a weak requirement, they are *no* requirement: a food
    that has not been measured does not get gated on a guess, exactly as
    abstract advice requires no entity on the long-form side.
    """

    required_entity: str
    required_attributes: tuple[str, ...] = ()
    forbidden_attributes: tuple[str, ...] = ()
    forbidden_dominant_entities: tuple[str, ...] = COMMON_DOMINANT_DISTRACTORS
    context_requirements: tuple[str, ...] = ()
    #: Searches that name the state rather than the food, for the repair pass.
    #: "manzana" is what returned the cake; "whole raw apple with the skin on"
    #: is what does not.
    queries: tuple[str, ...] = ()
    #: The short English phrase the *ranker* scores a candidate against, which
    #: is a different job from the four probes and needs a different sentence.
    #: A beat's own ``search_text`` was written to find footage and names the
    #: furniture it expects to find it on - "a whole red apple on a wooden
    #: table" - and a prompt naming the table is a prompt about the table, the
    #: same fault the context prompts had. This names the food and its state
    #: and nothing else.
    visual_intent: str = ""

    @property
    def entity(self) -> VisualEntity:
        return BY_NAME[self.required_entity]


def _requirement(
    food: str,
    required: Sequence[str] = (),
    forbidden: Sequence[str] = (),
    dominant: Sequence[str] = (),
    context: Sequence[str] = (),
    queries: Sequence[str] = (),
    intent: str = "",
) -> VisualRequirement:
    return VisualRequirement(
        required_entity=food,
        required_attributes=tuple(required),
        forbidden_attributes=tuple(forbidden),
        forbidden_dominant_entities=(*COMMON_DOMINANT_DISTRACTORS, *dominant),
        context_requirements=tuple(context),
        queries=tuple(queries),
        visual_intent=intent,
    )


#: The foods whose state has been written down, which is the five the test
#: reel names plus the two whose state is the entire point of the item.
#:
#: Written from observed failures and nothing else. Speculating about the
#: state of a food no render has got wrong would add gates with no evidence
#: behind them, and every gate costs good footage.
REQUIREMENTS: dict[str, VisualRequirement] = {
    # The brief's own example, and the one that shipped twice: a cake and a
    # peeled apple against a line that says "con piel".
    "manzana": _requirement(
        "manzana",
        # Not "is the skin absent". Absence is the question a contrastive
        # model is worst at, and the benchmark says so plainly: asking it
        # (run 34113587132, "absence") keeps five of six raw apples and
        # rejects four of six peeled ones. Describing the *surface* on one
        # side and the cut flesh on the other - both positives, both about
        # something visible - keeps six of six and rejects five of six, on
        # the same clips and the same model. The backend was never the
        # limit: full-precision ViT-L/14 scores identically to the quantized
        # one on all three formulations.
        required=(
            "apples with glossy red and green surfaces",
            "apples on a tree with their skin on",
        ),
        forbidden=(
            "pale wet apple flesh being cut",
            "apple pieces in pastry and syrup",
            "an apple drink in a glass",
        ),
        context=(
            "fresh apples clearly visible as the main subject",
            "apples filling the frame",
        ),
        queries=(
            "whole raw red apple with skin close up",
            "unpeeled apples on a wooden table",
            "fresh apple with skin sliced on a board",
        ),
        intent="a fresh whole apple with its skin, as the main subject",
    ),
    # A dog owned one strawberry frame; "strawberry" also returns milkshakes,
    # ice cream and cake, which are not what "menos carbohidratos por racion"
    # is about.
    "fresas": _requirement(
        "fresas",
        required=(
            "fresh raw whole strawberries",
            "ripe red strawberries with green leaves",
        ),
        forbidden=(
            "a strawberry milkshake",
            "strawberry ice cream",
            "a strawberry cake or dessert",
            "a strawberry flavoured yogurt drink",
        ),
        dominant=(
            "a mixed fruit platter of many different fruits",
        ),
        context=(
            "fresh strawberries clearly visible as the main subject",
            "strawberries filling the frame",
        ),
        queries=(
            "fresh whole strawberries in a bowl close up",
            "ripe raw strawberries on a table",
        ),
        intent="fresh whole strawberries as the main food subject",
    ),
    # The one food the probe cannot identify on its own (0.0/0.0 against
    # strawberries). Its state requirement is written the same way as the
    # others so the measurement covers it, and nothing here tries to buy the
    # entity number back.
    "frambuesas": _requirement(
        "frambuesas",
        required=(
            "fresh raw whole raspberries",
            "ripe red raspberries in a punnet",
        ),
        forbidden=(
            "raspberry jam",
            "a raspberry dessert or cake",
            "a raspberry smoothie",
        ),
        dominant=(
            "a mixed fruit platter of many different fruits",
        ),
        context=(
            "fresh raspberries clearly visible as the main subject",
            "raspberries filling the frame",
        ),
        queries=(
            "fresh whole raspberries in a punnet close up",
            "ripe raw raspberries in a white bowl",
        ),
        intent="fresh raspberries as the main food subject",
    ),
    # A coconut shared the kiwi frame, and "tropical fruit" is what a kiwi
    # search drifts into.
    "kiwi": _requirement(
        "kiwi",
        required=(
            "fresh raw kiwi fruit with green flesh",
            "a kiwi fruit cut in half showing its seeds",
        ),
        forbidden=(
            "a kiwi smoothie or juice",
            "a kiwi dessert or cake",
        ),
        dominant=(
            "a coconut",
            "a tropical fruit platter of many different fruits",
            "a pineapple",
        ),
        context=(
            "fresh kiwi fruit clearly visible as the main subject",
            "kiwi fruit filling the frame",
        ),
        queries=(
            "fresh kiwi fruit cut in half close up",
            "raw green kiwi slices on a plate",
        ),
        intent="fresh kiwi fruit, whole or halved, as the main subject",
    ),
    # The brief accepts whole or cut, and rejects the branded tub where no
    # fruit is visible - which is what WRONG_CONTEXT is for.
    "aguacate": _requirement(
        "aguacate",
        # The state probe here was asking the wrong question. It described
        # cuts - halved, sliced - so a *whole* avocado, which is dark bumpy
        # skin and no green flesh at all, lost to "a tub of packaged
        # guacamole dip" on five clips in six (run 34113587132). The brief
        # is right that whole, halved and sliced should all pass, and the
        # reason they can is that the entity probe has already established
        # this is an avocado: the only thing left for the state to exclude
        # is the form where the fruit stops being visible food - a drink or
        # a puree.
        required=(
            "a whole or cut avocado",
            "avocado halves or slices on a plate",
            "avocado slices on toast",
        ),
        forbidden=(
            "a green drink in a tall glass",
            "a bowl of smooth green puree with no fruit visible",
        ),
        context=(
            "avocado clearly visible and identifiable as the main subject",
            "avocados filling the frame",
        ),
        queries=(
            "fresh raw avocado cut in half close up",
            "whole avocados on a wooden board",
        ),
        intent="a fresh avocado, whole or cut open, as the main subject",
    ),
    # The juice item is about the juice, and the state is inverted: here the
    # glass is right and the whole fruit is the failure. Written because
    # "cambiar la fruta entera por zumo" is the one item whose picture the
    # entity probe would happily satisfy with the thing the line warns about.
    "zumo": _requirement(
        "zumo",
        required=(
            "a glass of fruit juice",
            "juice being poured into a glass",
        ),
        forbidden=(
            "whole uncut fruit with no glass",
        ),
        # The one place a container belongs: "cambiar la fruta entera por
        # zumo" warns about the drink, so a picture of it has to contain the
        # glass. Everywhere else the container is furniture.
        context=(
            "a glass of juice clearly visible as the main subject",
        ),
        queries=(
            "glass of fresh orange juice on a table close up",
        ),
        intent="a glass of fruit juice as the main subject",
    ),
    # "que ponga integral en el envase" is advice about a label, and the
    # failure is white bread, which is a state rather than a different food.
    "pan_integral": _requirement(
        "pan_integral",
        required=(
            "dark wholegrain bread with visible grains",
            "sliced brown wholemeal bread",
        ),
        forbidden=(
            "white bread with a pale crumb",
            "a sweet pastry or cake",
        ),
        context=(
            "wholegrain bread clearly visible as the main subject",
        ),
        queries=(
            "dark whole grain bread loaf sliced close up",
        ),
        intent="dark wholegrain bread with visible grains, as the main subject",
    ),
}


def requirement_for_food(entity: VisualEntity | None) -> VisualRequirement | None:
    """The full requirement for a food, or the bare-entity one.

    A food with nothing written down still gets the dominance check, because
    a dog owning the frame is wrong whatever is behind it and that list is
    not a guess about this food - it is a list of what actually happened.
    """

    if entity is None:
        return None
    existing = REQUIREMENTS.get(entity.name)
    if existing is not None:
        return existing
    return VisualRequirement(required_entity=entity.name, queries=entity.queries)


def required_visual_for(beat: Any) -> VisualRequirement | None:
    """What this beat's footage has to satisfy, if anything."""

    return requirement_for_food(required_food_for(beat))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

#: The cuts for the three new probes.
#:
#: Same shape as :data:`FOOD_IDENTIFY_PASS` - the share of frames in which
#: the required side ranks above every forbidden one - and set at the middle
#: of the range on purpose, because with three frames the only reachable
#: values are 0, 1/3, 2/3 and 1 and 0.5 means "most frames". They are a
#: hypothesis until ``tools/reel_grounding_check.py`` has scored the nine
#: piles of real footage; what the measurement is allowed to move is these
#: numbers, and never the definition of a pass.
FOOD_STATE_PASS = 0.5
FOOD_CONTEXT_PASS = 0.5
FOOD_SUBJECT_PASS = 0.5


def _identify(
    rows: Sequence[Sequence[float]],
    start: int,
    positives: int,
    negatives: Sequence[str],
) -> tuple[float, str, int]:
    """Share of frames where a positive outranks every negative.

    ``rows`` is the whole similarity matrix and ``start`` is where this
    probe's prompts begin in it, so four questions share one encode. Returns
    (share, the negative that won most often, frames counted).
    """

    if positives <= 0 or not negatives:
        return 0.0, "", 0
    stop = start + positives + len(negatives)
    wins = counted = 0
    losers: dict[str, int] = {}
    for row in rows:
        if len(row) < stop:
            continue
        counted += 1
        window = row[start:stop]
        best = max(range(len(window)), key=lambda i: window[i])
        if best < positives:
            wins += 1
        else:
            name = negatives[best - positives]
            losers[name] = losers.get(name, 0) + 1
    if not counted:
        return 0.0, "", 0
    top = max(losers.items(), key=lambda kv: kv[1])[0] if losers else ""
    return wins / counted, top, counted


@dataclass
class FoodGrounding:
    """Whether one clip shows the right food, in the right state, as the subject.

    Compatible with :class:`~vidfactory.entities.EntityGrounding` where the
    pipeline and the report already read it - ``checked``, ``passed``,
    ``score``, ``failed``, ``top_distractor`` - and richer where the verdict
    now has more than one reason to be no.

    ``score`` is the **weakest** probe that ran, not their average. An
    average is exactly the compensation this layer exists to refuse: apple
    1.00 and state 0.00 must not come out at 0.50 and pass.
    """

    entity: str = ""
    labels: tuple[str, ...] = ()
    checked: bool = False
    passed: bool = True
    score: float = 0.0
    entity_presence_score: float = 0.0
    entity_presence_passed: bool = True
    entity_presence_checked: bool = False
    state_match_score: float = 0.0
    state_passed: bool = True
    state_checked: bool = False
    context_match_score: float = 0.0
    context_passed: bool = True
    context_checked: bool = False
    dominant_subject_score: float = 0.0
    distractor_dominance_score: float = 0.0
    subject_passed: bool = True
    subject_checked: bool = False
    top_distractor: str = ""
    failed_on: tuple[str, ...] = ()
    detail: str = ""

    @property
    def required(self) -> bool:
        return bool(self.entity)

    @property
    def failed(self) -> bool:
        return self.required and self.checked and not self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_visual_entity": self.entity,
            "required_visual_labels": list(self.labels),
            "entity_grounding_checked": self.checked,
            "entity_grounding_passed": self.passed,
            "entity_grounding_score": round(self.score, 3),
            "entity_presence_score": round(self.entity_presence_score, 3),
            "state_match_score": round(self.state_match_score, 3),
            "context_match_score": round(self.context_match_score, 3),
            "dominant_subject_score": round(self.dominant_subject_score, 3),
            "distractor_dominance_score": round(self.distractor_dominance_score, 3),
            "failed_on": list(self.failed_on),
            "looked_like": self.top_distractor,
            "entity_grounding_detail": self.detail,
        }


def requirement_prompts(
    requirement: VisualRequirement, wrong_context: Sequence[str] = WRONG_CONTEXT
) -> tuple[list[str], dict[str, int]]:
    """Every prompt the four probes need, and where each one starts.

    One list, because one encode of the frames answers all four questions and
    four encodes would answer them no better at four times the cost.
    """

    entity = requirement.entity
    prompts: list[str] = []
    offsets: dict[str, int] = {}

    offsets["entity"] = len(prompts)
    prompts.extend(entity.positives)
    prompts.extend(entity.competitors)

    offsets["state"] = len(prompts)
    prompts.extend(requirement.required_attributes)
    prompts.extend(requirement.forbidden_attributes)

    offsets["context"] = len(prompts)
    prompts.extend(requirement.context_requirements)
    if requirement.context_requirements:
        prompts.extend(wrong_context)

    # The dominance probe reuses the entity's own positives - the question is
    # whether the food outranks the dog, and "a bowl of red strawberries" is
    # already the best statement of the food there is - so only the
    # distractors are added here, and the scorer is given both slices.
    offsets["dominant"] = len(prompts)
    prompts.extend(requirement.forbidden_dominant_entities)
    return prompts, offsets


def score_requirement(
    requirement: VisualRequirement,
    per_frame: Sequence[Sequence[float]],
    wrong_context: Sequence[str] = WRONG_CONTEXT,
) -> FoodGrounding:
    """The four probes, combined as a conjunction.

    Each is the same question in a different vocabulary: of the frames we
    could read, in how many did the required side rank above every forbidden
    one? Each has its own cut, each is reported separately, and the verdict
    is the ``and`` of the ones that ran - so a probe with nothing written
    down for this food abstains rather than passing something.
    """

    entity = requirement.entity
    blank = FoodGrounding(entity=entity.name, labels=entity.labels)
    if not per_frame:
        return blank

    prompts, offsets = requirement_prompts(requirement, wrong_context)
    presence, presence_loser, counted = _identify(
        per_frame, offsets["entity"], len(entity.positives), entity.competitors
    )
    if not counted:
        return blank

    state, state_loser, state_frames = _identify(
        per_frame, offsets["state"], len(requirement.required_attributes),
        requirement.forbidden_attributes,
    )
    context, context_loser, context_frames = _identify(
        per_frame, offsets["context"], len(requirement.context_requirements),
        wrong_context if requirement.context_requirements else (),
    )
    # The food against what owns the frame instead. The positives are the
    # entity's, which sit at the front of the matrix, so this probe reads two
    # separate slices and cannot use ``_identify``'s single window.
    subject, subject_loser, subject_frames = _identify_split(
        per_frame,
        (offsets["entity"], len(entity.positives)),
        (offsets["dominant"], requirement.forbidden_dominant_entities),
    )

    failed: list[str] = []
    scores: list[float] = [presence]
    presence_ok = presence >= FOOD_IDENTIFY_PASS
    if not presence_ok:
        failed.append("entity")
    state_ok = state >= FOOD_STATE_PASS if state_frames else True
    if state_frames:
        scores.append(state)
        if not state_ok:
            failed.append("state")
    context_ok = context >= FOOD_CONTEXT_PASS if context_frames else True
    if context_frames:
        scores.append(context)
        if not context_ok:
            failed.append("context")
    subject_ok = subject >= FOOD_SUBJECT_PASS if subject_frames else True
    if subject_frames:
        scores.append(subject)
        if not subject_ok:
            failed.append("dominant_subject")

    passed = not failed
    # Whichever probe came closest to saying no, named. The entity probe's
    # loser is the right answer when the food itself is wrong; otherwise the
    # thing that actually beat it is more useful to a reviewer than the
    # runner-up fruit.
    loser = (
        presence_loser if "entity" in failed
        else state_loser if "state" in failed
        else subject_loser if "dominant_subject" in failed
        else context_loser if "context" in failed
        else presence_loser
    )
    label = entity.labels[0]
    return FoodGrounding(
        entity=entity.name,
        labels=entity.labels,
        checked=True,
        passed=passed,
        score=round(min(scores), 3),
        entity_presence_score=round(presence, 3),
        entity_presence_passed=presence_ok,
        entity_presence_checked=True,
        state_match_score=round(state, 3),
        state_passed=state_ok,
        state_checked=bool(state_frames),
        context_match_score=round(context, 3),
        context_passed=context_ok,
        context_checked=bool(context_frames),
        dominant_subject_score=round(subject, 3),
        distractor_dominance_score=round(1.0 - subject, 3),
        subject_passed=subject_ok,
        subject_checked=bool(subject_frames),
        top_distractor=loser,
        failed_on=tuple(failed),
        detail=(
            f"{label}: entity {presence:.2f}, state {state:.2f}, "
            f"context {context:.2f}, subject {subject:.2f}"
            + ("" if passed else
               f" - failed on {', '.join(failed)}"
               + (f"; looked like {loser!r}" if loser else ""))
        ),
    )


def _identify_split(
    rows: Sequence[Sequence[float]],
    positives: tuple[int, int],
    negatives: tuple[int, Sequence[str]],
) -> tuple[float, str, int]:
    """:func:`_identify` where the two sides are not adjacent in the matrix."""

    start, count = positives
    neg_start, names = negatives
    if count <= 0 or not names:
        return 0.0, "", 0
    wins = counted = 0
    losers: dict[str, int] = {}
    for row in rows:
        if len(row) < max(start + count, neg_start + len(names)):
            continue
        counted += 1
        best_positive = max(row[start:start + count])
        window = row[neg_start:neg_start + len(names)]
        best_negative = max(window)
        if best_positive >= best_negative:
            wins += 1
        else:
            losers[names[window.index(best_negative)]] = (
                losers.get(names[window.index(best_negative)], 0) + 1
            )
    if not counted:
        return 0.0, "", 0
    top = max(losers.items(), key=lambda kv: kv[1])[0] if losers else ""
    return wins / counted, top, counted


def ground_requirement(
    analyzer: Any,
    frames: Sequence[Any],
    requirement: VisualRequirement | None,
    wrong_context: Sequence[str] = WRONG_CONTEXT,
) -> FoodGrounding:
    """Score one clip against one beat's whole requirement.

    On the validated verifier, never on the ranker. MobileCLIP-S0 was
    measured at chance on plain "which fruit is this"; asking it which
    *state* the fruit is in would be asking a harder question of a model that
    failed the easier one.
    """

    if requirement is None:
        return FoodGrounding()
    prompts, _ = requirement_prompts(requirement, wrong_context)
    per_frame = analyzer.probe_frames(frames, prompts, use_claim_model=True)
    return score_requirement(requirement, per_frame, wrong_context)


def state_repair_queries(
    requirement: VisualRequirement, spent: Sequence[str] = ()
) -> list[str]:
    """What to search when the food was right and the shot was not.

    The requirement's own queries first, because they name the state that
    failed - "whole raw apple with the skin on" is a different search from
    "manzana", and the second one is what returned the cake.
    """

    used = {str(q).strip().lower() for q in spent}
    ordered = [*requirement.queries, *requirement.entity.queries]
    out: list[str] = []
    for query in ordered:
        key = query.strip().lower()
        if key and key not in used:
            used.add(key)
            out.append(query.strip())
    return out
