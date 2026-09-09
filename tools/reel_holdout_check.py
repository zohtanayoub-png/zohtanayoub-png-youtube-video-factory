#!/usr/bin/env python3
"""Held-out measurement. Nothing here scores a change on the clips that shaped it.

The four-probe conjunction cut false positives from 66.7% to 20.8% and pushed
false negatives from 26.7% to 50.0%, and both halves of that came off the same
fifty-four clips. Those clips have now done their job: they are what the
prompts were written against, so a prompt rewritten in the light of them
cannot be graded on them without the grade meaning nothing.

``data/calibration/reel_grounding_dev_clips.json`` freezes the fifty-four
provider ids and the nine queries that produced them. Every pile this tool
builds excludes both - a different query, and an explicit id filter under it -
so a number printed here is a number about footage the prompts have never
seen.

Four questions, four commands, and they are deliberately separate runs:

``presentation`` is a valid strawberry still a strawberry when it is not in
               a bowl? The entity probe alone and the whole conjunction on
               the same frames, because reporting one without the other is
               what made "the conjunction is too strict" look true.
``entity``     can the probe see the fruit in every shape it arrives in -
               whole, cut and piled? The layer under all the others, and the
               one the second held-out benchmark pointed at.
``berries``    does the raspberry wording+crop candidate survive fresh
               footage, against strawberry, blackberry and blueberry? A
               confusion matrix, because "kept 5 of 8" hides which berry the
               other three turned into.
``avocado``    which avocado states a generic ``aguacate`` beat should accept,
               decided on its own calibration piles - whole, halved, sliced,
               toast, guacamole, smoothie, unrelated green - and never on the
               clips that exposed the smoothie problem.
``apple``      can any backend answer "is this apple raw, and is its skin
               visible" at all? Backends and prompt formulations together,
               with load time, per-frame runtime and peak memory beside the
               accuracy, because a verifier that cannot run on a free runner
               is not a candidate.
``apple-state`` which wording of "manzana con piel" keeps an apple that is
               an apple. Ten presentations against eight formulations, none of
               which names a tree, a plate, a table or a board: the state is a
               fact about the fruit and the location is not.
``apple-holdout`` the applied apple wording on fresh apple footage, per class.
``apple-final`` one named negative prompt against the one that ships, on a
               third apple set, with the accept rule written down first.
``sharpness``  is a window *readable*, not merely correct? The used-segment
               gate passed a blurred apple at 1.00 on all four probes, so
               this measures ``window_quality`` on fresh food footage and
               prints a three-frame strip of every window beside its numbers.
               It chooses nothing: the labels are written by a person into
               ``data/calibration/window_readability_labels.json`` and the
               floor is read off those.
``holdout``    the whole gate on fresh piles: precision and recall, overall
               and per food and per state.

Run them with the ``reel-holdout-check`` task on the video workflow.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import resource
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from vidfactory.config import load_config
from vidfactory.downloader import ClipDownloader
from vidfactory.logging_utils import get_logger, setup_logging
from vidfactory.reels.pipeline import window_starts
from vidfactory.reels.foods import (
    BY_NAME,
    WRONG_CONTEXT,
    FOOD_IDENTIFY_PASS,
    ground_requirement,
    identify_food,
    requirement_for_food,
    requirement_prompts,
    score_requirement,
)
from vidfactory.stock import build_providers
from vidfactory.visual_analysis import (
    VisualAnalyzer,
    crop_center,
    sample_frames,
    decode_frame,
    focus_statistics,
    measure,
    segment_frames,
    segment_positions,
    window_quality,
)
from vidfactory.visual_model import load_model

log = get_logger("HOLDOUT")

FROZEN = Path("data/calibration/reel_grounding_dev_clips.json")


def frozen() -> tuple[set[str], set[str]]:
    """(clip ids, queries) that development already spent."""

    if not FROZEN.exists():                                # pragma: no cover
        log.warning("no frozen development set at %s", FROZEN)
        return set(), set()
    data = json.loads(FROZEN.read_text(encoding="utf-8"))
    return set(data.get("clips") or []), {
        q.strip().lower() for q in data.get("burned_queries") or []
    }


@dataclass(frozen=True)
class Pile:
    """One search whose answer a human already knows, on unseen footage."""

    name: str
    query: str
    #: What the pile is *of*, for a confusion matrix.
    truth: str = ""
    #: Whether a beat requiring ``food`` should accept it.
    accept: bool = True
    food: str = ""
    page: int = 1


# ---------------------------------------------------------------------------
# The piles. Every query differs from the nine the development set spent.
# ---------------------------------------------------------------------------

BERRY_PILES: tuple[Pile, ...] = (
    Pile("raspberries", "raspberries tipped onto a slate slab", "frambuesas"),
    Pile("strawberries", "strawberries hulled and heaped in a colander", "fresas"),
    Pile("blackberries", "blackberries gathered in cupped hands", "moras"),
    Pile("blueberries", "blueberries spilling from a paper bag", "arandanos"),
)

#: Label groups for the berry confusion matrix. Local to the measurement -
#: blackberries and blueberries are not foods a reel narrates, they are what a
#: raspberry gets confused with, and the registry is not the place for that.
BERRY_LABELS: dict[str, tuple[str, ...]] = {
    "frambuesas": ("fresh raspberries", "a bowl of raspberries", "raspberries close up"),
    "fresas": ("fresh strawberries", "a bowl of red strawberries",
               "whole strawberries close up"),
    "moras": ("fresh blackberries", "a bowl of blackberries", "blackberries close up"),
    "arandanos": ("fresh blueberries", "a bowl of blueberries", "blueberries close up"),
}

#: The candidate wording the development run pointed at, stated once.
BERRY_CANDIDATE: dict[str, tuple[str, ...]] = {
    "frambuesas": ("a punnet of raspberries stacked in rows",
                   "many small raspberries filling a bowl",
                   "raspberries piled on a wooden table"),
    "fresas": ("a punnet of strawberries stacked in rows",
               "many red strawberries filling a bowl",
               "strawberries piled on a wooden table"),
    "moras": ("a punnet of blackberries stacked in rows",
              "many dark blackberries filling a bowl",
              "blackberries piled on a wooden table"),
    "arandanos": ("a punnet of blueberries stacked in rows",
                  "many small blueberries filling a bowl",
                  "blueberries piled on a wooden table"),
}

AVOCADO_PILES: tuple[Pile, ...] = (
    Pile("whole avocado", "whole avocados in a basket", "whole", True, "aguacate"),
    Pile("halved avocado", "avocado cut open showing the pit", "halved", True, "aguacate"),
    Pile("sliced avocado", "avocado slices fanned on a plate", "sliced", True, "aguacate"),
    Pile("avocado toast", "avocado toast breakfast plate", "toast", True, "aguacate"),
    Pile("guacamole", "bowl of guacamole with tortilla chips", "guacamole", False, "aguacate"),
    Pile("avocado smoothie", "green avocado smoothie in a tall glass", "smoothie", False, "aguacate"),
    Pile("unrelated green", "fresh green peas and broccoli on a table", "other", False, "aguacate"),
)

APPLE_PILES: tuple[Pile, ...] = (
    Pile("raw apple with skin", "red apples on a branch in an orchard", "raw", True, "manzana"),
    Pile("peeled apple", "peeling an apple with a knife", "peeled", False, "manzana"),
    Pile("apple dessert", "homemade apple crumble in a baking dish", "dessert", False, "manzana"),
    Pile("apple juice", "pouring apple juice into a glass", "juice", False, "manzana"),
)

#: Entity-layer calibration. The held-out benchmark said a *whole* avocado
#: survives twice in six and a raw apple in a market crate once - and that
#: the probe doing the rejecting is the entity probe, not the state layer
#: above it. So these piles are about presentation rather than about state:
#: the same fruit, whole and cut and in bulk, against what the search returns
#: instead of it.
ENTITY_PILES: tuple[Pile, ...] = (
    Pile("whole avocados", "ripe avocados stacked in a bowl", "whole", True, "aguacate"),
    Pile("cut avocado", "avocado sliced open on a chopping board", "cut", True, "aguacate"),
    Pile("not avocado", "green pears and limes on a table", "other", False, "aguacate"),
    Pile("apples in bulk", "apples on a market stall in autumn", "bulk", True, "manzana"),
    Pile("cut apple", "apple slices on a white plate", "cut", True, "manzana"),
    Pile("not apple", "oranges piled on a market stall", "other", False, "manzana"),
)

#: Candidate positive sets. The shipped ones are first so the table reads as
#: a before/after. Every candidate is written from the *diagnosis* - name the
#: presentations a beat legitimately gets, whole and cut and piled - and not
#: from the clips that exposed the gap, which are in the manifest.
ENTITY_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "aguacate": {
        "shipped": ("a halved avocado", "avocado cut in half with the stone",
                    "sliced avocado on a board"),
        "whole-and-cut": ("a whole avocado with dark bumpy skin",
                          "a halved avocado with the stone",
                          "sliced green avocado"),
        "whole-cut-and-many": ("a whole avocado with dark bumpy skin",
                               "a halved avocado with the stone",
                               "sliced green avocado",
                               "a pile of avocados"),
    },
    "manzana": {
        "shipped": ("a red apple", "a whole apple with skin",
                    "sliced apple on a board", "a green apple"),
        "single-and-many": ("a red apple", "a green apple",
                            "sliced apple on a board",
                            "a crate of apples at a market",
                            "many apples piled together"),
    },
}

#: Presentation. The third benchmark rejected strawberries on linen, apples
#: in market boxes and raspberries in a glass jar - and the context prompts
#: say "in a bowl as the main subject" and "on a kitchen table". A prompt
#: naming the crockery is a prompt about the crockery, so these piles vary
#: the presentation on purpose and hold the food constant.
PRESENTATION_PILES: tuple[Pile, ...] = (
    Pile("strawberries in a bowl", "strawberries heaped in a white bowl", "bowl", True, "fresas"),
    Pile("strawberries on a plate", "strawberries arranged on a dessert plate", "plate", True, "fresas"),
    Pile("strawberries on linen", "strawberries resting on folded linen", "linen", True, "fresas"),
    Pile("strawberries on wood", "strawberries on a dark wooden board", "board", True, "fresas"),
    Pile("strawberries in a box", "punnets of strawberries in a supermarket box", "box", True, "fresas"),
    Pile("strawberries held", "hand holding a single ripe strawberry", "held", True, "fresas"),
    Pile("not strawberries", "fresh cherries with stalks in a dish", "other", False, "fresas"),

    Pile("raspberries in a bowl", "raspberries in a shallow ceramic bowl", "bowl", True, "frambuesas"),
    Pile("raspberries in a jar", "raspberries filling a clear glass jar", "jar", True, "frambuesas"),
    Pile("raspberries in a punnet", "raspberries in a cardboard punnet", "punnet", True, "frambuesas"),
    Pile("raspberries loose", "raspberries scattered loose on a surface", "loose", True, "frambuesas"),
    Pile("raspberries held", "hand holding a few raspberries", "held", True, "frambuesas"),
    Pile("not raspberries", "blackberries and blueberries mixed together", "other", False, "frambuesas"),

    Pile("a single apple", "one red apple standing alone", "single", True, "manzana"),
    Pile("apples in a box", "apples packed in a cardboard box", "box", True, "manzana"),
    Pile("apples piled", "apples heaped high at a fruit stand", "pile", True, "manzana"),
    Pile("an apple held", "hand holding up a red apple", "held", True, "manzana"),
    Pile("apple on a board", "apple beside a knife on a cutting board", "board", True, "manzana"),
    Pile("not apples", "pears and oranges together in a fruit bowl", "other", False, "manzana"),

    Pile("whole avocados", "avocados resting on a stone counter", "whole", True, "aguacate"),
    Pile("halved avocado", "avocado opened to show the stone", "halved", True, "aguacate"),
    Pile("sliced avocado", "avocado cut into thin green slices", "sliced", True, "aguacate"),
    Pile("many avocados", "many avocados spread across a surface", "many", True, "aguacate"),
    Pile("not avocados", "courgettes and green peppers on a board", "other", False, "aguacate"),

    Pile("whole kiwi", "kiwi fruit with fuzzy brown skin", "whole", True, "kiwi"),
    Pile("halved kiwi", "kiwi opened to show the green centre", "halved", True, "kiwi"),
    Pile("sliced kiwi", "kiwi cut into thin green wheels", "sliced", True, "kiwi"),
    Pile("not kiwi", "limes and green apples side by side", "other", False, "kiwi"),

    # The rejections that must survive the rewrite. A context prompt that
    # stops naming the crockery must not also stop rejecting the dessert.
    Pile("apple dessert", "apple pie cooling on a rack", "dessert", False, "manzana"),
    Pile("peeled apple", "apple stripped of its skin on a chopping block", "peeled", False, "manzana"),
    Pile("strawberry dessert", "strawberry mousse in a dessert glass", "processed", False, "fresas"),
    Pile("avocado smoothie", "avocado shake blended in a tall tumbler", "smoothie", False, "aguacate"),
    Pile("tropical platter", "sliced mango papaya and pineapple platter", "mixed", False, "kiwi"),
)

#: Candidate context wordings. The shipped one names the container; the
#: others name the food. The third exists because one of the shared
#: wrong-context prompts is "a supermarket shelf full of packaged goods",
#: and a supermarket box of strawberries is a presentation the brief wants
#: kept - so whether that negative is doing harm is a question, not a guess.
CONTEXT_CANDIDATES: dict[str, dict[str, Any]] = {
    # The wording that shipped before this cycle, written out here rather
    # than read from the module: the module has moved on, and "before" has
    # to keep meaning what it meant.
    "container-named (before)": {
        "context": {
            "fresas": ("fresh strawberries in a bowl as the main subject",
                       "whole strawberries on a kitchen table"),
            "frambuesas": ("fresh raspberries in a bowl as the main subject",
                           "whole raspberries on a wooden table"),
            "manzana": ("fresh whole apples on a kitchen table",
                        "raw apples in a bowl as the main subject"),
            "aguacate": ("fresh avocados on a wooden board as the main subject",
                         "a halved avocado on a plate"),
            "kiwi": ("fresh kiwi fruit on a plate as the main subject",
                     "whole and halved kiwi fruit on a table"),
        },
        "wrong": None,
    },
    # What the module now says.
    "food-centred (after)": {"context": None, "wrong": None},
    # One of the shared negatives is "a supermarket shelf full of packaged
    # goods", and a supermarket box of strawberries is a presentation worth
    # keeping - so whether that prompt costs anything is a question rather
    # than a guess.
    "food-centred, no shelf": {
        "context": None,
        "wrong": ("a branded supermarket product in printed packaging",
                  "a printed logo or an advertisement"),
    },
}

#: Apple state. The presentation run put ``manzana`` at entity recall 0.800
#: and conjunction recall 0.400 at precision 1.000 - so half the valid apple
#: footage is lost *between* the two, which is the state probe, and the state
#: probe says "apples on a tree with their skin on". A single apple on a
#: board is not on a tree. The requirement is ``manzana con piel``: the state
#: has to describe the apple, not where the apple is standing.
#:
#: Ten presentations, every one of them new footage - every apple query the
#: previous eight runs used is in the manifest, so none of them can appear
#: here. The oranges are not a presentation; they are the failure this whole
#: layer was built to stop, and the success condition names them.
APPLE_STATE_PILES: tuple[Pile, ...] = (
    Pile("a single whole apple", "a single glossy apple on a bare surface",
         "whole", True, "manzana"),
    Pile("apples in a pile", "a mound of apples at an autumn fruit stand",
         "piled", True, "manzana"),
    Pile("apples in a market box", "wooden crates full of apples for sale",
         "piled", True, "manzana"),
    Pile("an apple in a hand", "a person picking up an apple in their hand",
         "held", True, "manzana"),
    Pile("an apple on a board", "an apple resting on a wooden chopping board",
         "board", True, "manzana"),
    Pile("sliced, peel visible", "apple wedges with the red skin on the edge",
         "sliced_with_skin", True, "manzana"),
    Pile("peeled apple", "a bare peeled apple with the skin removed",
         "peeled", False, "manzana"),
    Pile("apple cake", "a slice of apple cake on a fork",
         "dessert", False, "manzana"),
    Pile("apple pie", "apple pie with a lattice crust",
         "dessert", False, "manzana"),
    Pile("apple juice", "a glass of apple juice on a counter",
         "juice", False, "manzana"),
    Pile("oranges, not apples", "a pile of oranges at a fruit stall",
         "orange", False, "manzana"),
)

#: The formulations, and what each one is asking.
#:
#: The brief's rule is the whole design: **the positive describes the apple's
#: state and never its location**, so no candidate here contains tree, plate,
#: table, basket, kitchen or cutting board. What is deliberately varied
#: beside the positives is the *negative* set, because "pale wet apple flesh
#: being cut" is a negative that a legitimately sliced apple with its peel
#: still on matches, and that is one of the presentations the brief requires
#: accepted.
APPLE_STATE_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    # What ships today, written out here rather than read from the module,
    # so "before" keeps meaning what it meant when the number was taken.
    "shipped (before)": {
        "required": ("apples with glossy red and green surfaces",
                     "apples on a tree with their skin on"),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
    # The shipped wording with the orchard clause deleted and nothing else
    # changed. If the location is the whole fault, this is where it shows.
    "no orchard": {
        "required": ("apples with glossy red and green surfaces",),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
    "visible skin": {
        "required": ("a fresh apple with visible skin",),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
    "unpeeled": {
        "required": ("a fresh unpeeled apple",),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
    "natural peel": {
        "required": ("a raw apple with its natural peel visible",),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
    # All three of the brief's wordings together, still against the shipped
    # negatives: does saying it three ways beat saying it once?
    "all three skin wordings": {
        "required": ("a fresh apple with visible skin",
                     "a fresh unpeeled apple",
                     "a raw apple with its natural peel visible"),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
    # The same positives against negatives that name the states the brief
    # rejects - peeled, baked, juiced - instead of naming a cut. A wedge of
    # apple with its peel on the edge is a cut, and it is one of the shapes
    # that has to pass.
    "skin wordings, state negatives": {
        "required": ("a fresh apple with visible skin",
                     "a fresh unpeeled apple",
                     "a raw apple with its natural peel visible"),
        "forbidden": ("an apple peeled bare with its skin removed",
                      "cooked apple baked into a cake or a pie",
                      "apple juice in a glass"),
    },
    # One positive, the state negatives. The cheapest rule that could work.
    "visible skin, state negatives": {
        "required": ("a fresh apple with visible skin",),
        "forbidden": ("an apple peeled bare with its skin removed",
                      "cooked apple baked into a cake or a pie",
                      "apple juice in a glass"),
    },
}

#: The held-out apple set: the classes the brief asks to be reported, on
#: footage the calibration above never touched. Written at the same time as
#: the calibration piles and never re-written after seeing a number, which is
#: the only thing that makes it held out.
APPLE_HOLDOUT_PILES: tuple[Pile, ...] = (
    Pile("whole apple", "one ripe apple photographed up close",
         "whole", True, "manzana"),
    Pile("apples piled", "apples stacked high in a shop display",
         "piled", True, "manzana"),
    Pile("apple in a hand", "holding a green apple up to the camera",
         "held", True, "manzana"),
    Pile("apple on a board", "a whole apple next to a knife blade",
         "board", True, "manzana"),
    Pile("sliced, peel visible", "quartered apple showing red peel and white flesh",
         "sliced_with_skin", True, "manzana"),
    Pile("peeled apple", "an apple stripped bare of its peel",
         "peeled", False, "manzana"),
    Pile("apple dessert", "warm apple turnover dusted with icing sugar",
         "dessert", False, "manzana"),
    Pile("apple juice", "apple juice being poured from a bottle",
         "juice", False, "manzana"),
    Pile("oranges, not apples", "oranges heaped in a wicker display",
         "orange", False, "manzana"),
)


#: The third apple set, and the last one. Two measurements now agree on a
#: single prompt: the calibration pile said replacing the state negatives
#: cuts the board losses from six in six to one and lifts recall from 0.472
#: to 0.611, and the held-out set - which had never been seen and was not
#: scored against any candidate - named ``pale wet apple flesh being cut``
#: as the closest distractor on **fourteen of the twenty-one** valid clips
#: it lost, including six of six apples on a board and four of five apple
#: wedges with the peel still on the edge.
#:
#: The brief requires both of those accepted, so that negative is wrong
#: against the specification and not merely low-scoring. What is wrong with
#: it is legible: an apple wedge does have pale flesh, and a whole apple
#: beside a knife looks like an apple about to be cut. What actually
#: distinguishes a *peeled* apple is that the pale surface is the whole
#: fruit, so that is what the replacement says - and nothing else moves.
#: The positives stay exactly as they are, because every rewording of them
#: measured worse.
APPLE_FINAL_PILES: tuple[Pile, ...] = (
    Pile("whole apple", "a bright red apple against a plain backdrop",
         "whole", True, "manzana"),
    Pile("apples piled", "hundreds of apples filling a harvest bin",
         "piled", True, "manzana"),
    Pile("apple in a hand", "a child holding an apple with both hands",
         "held", True, "manzana"),
    Pile("apple on a board", "a whole apple placed beside a chef's knife",
         "board", True, "manzana"),
    Pile("sliced, peel visible", "apple halves showing the skin and the core",
         "sliced_with_skin", True, "manzana"),
    Pile("peeled apple", "removing every bit of skin from an apple",
         "peeled", False, "manzana"),
    Pile("apple dessert", "apple crumble served warm in a bowl",
         "dessert", False, "manzana"),
    Pile("apple juice", "cloudy apple juice in a tall tumbler",
         "juice", False, "manzana"),
    Pile("oranges, not apples", "orange fruit stacked in a greengrocer window",
         "orange", False, "manzana"),
)

#: Two wordings and no more. A third would make this a calibration, and a
#: calibration is what the previous two runs already were: this set exists
#: to say whether one named change survives footage it has never seen.
APPLE_FINAL_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "shipped": {
        "required": ("apples with glossy red and green surfaces",
                     "apples on a tree with their skin on"),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
    # One prompt different. "Whose whole surface is" is the thing a peeled
    # apple has and a wedge with a red edge does not.
    "peeled names the whole surface": {
        "required": ("apples with glossy red and green surfaces",
                     "apples on a tree with their skin on"),
        "forbidden": ("an apple whose whole surface is pale bare flesh",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
}


#: Readability. The used-segment gate works - run 34331777135 moved four
#: crops and every one of the ten segments grounded at 1.00 or 0.67 - and it
#: still shipped an unreadable apple: ``pexels:37239365`` at 9.1-11.7s scores
#: 1.00 on all four probes over a blurred hand and a yellow smear. CLIP reads
#: "apple" confidently in a blur a person cannot.
#:
#: ``window_quality`` already measured it: sharpness 0.000, the floor, against
#: 0.21-0.52 for every other segment in that reel. What was missing is a
#: threshold, and a threshold guessed from the one clip that motivated it is
#: how a rule gets written that fits exactly one example.
#:
#: So: fresh queries over five foods, chosen to span the cinematography this
#: niche actually returns - macro detail, shallow depth of field, slow motion,
#: hands in the frame, and things being poured or dropped, which is where the
#: motion blur lives. Multiple windows per clip, because a single source
#: contains sharp and blurred moments and the sharp ones are the reason the
#: window search exists.
SHARPNESS_PILES: tuple[Pile, ...] = (
    Pile("strawberry macro", "macro close up of a strawberry surface",
         "fresas", True, "fresas"),
    Pile("strawberries dropped", "strawberries falling into water in slow motion",
         "fresas", True, "fresas"),
    Pile("raspberry picked", "a hand picking raspberries in slow motion",
         "frambuesas", True, "frambuesas"),
    Pile("raspberry turning", "raspberries turning slowly on a dark background",
         "frambuesas", True, "frambuesas"),
    Pile("kiwi sliced", "a kiwi being sliced in slow motion",
         "kiwi", True, "kiwi"),
    Pile("kiwi macro", "extreme macro of kiwi seeds and green flesh",
         "kiwi", True, "kiwi"),
    Pile("apple dropped", "an apple dropping into water in slow motion",
         "manzana", True, "manzana"),
    Pile("apple in hands", "hands polishing a red apple",
         "manzana", True, "manzana"),
    Pile("avocado turning", "avocado halves turning slowly",
         "aguacate", True, "aguacate"),
    Pile("avocado scooped", "a spoon scooping flesh out of an avocado",
         "aguacate", True, "aguacate"),
)

#: The window length the calibration measures at. The reel lays 2-4 second
#: shots and ``choose_window`` grounds whatever the layout asked for; three
#: seconds is the middle of that and is what ``visual_average_shot_seconds``
#: has come out at on every render so far.
SHARPNESS_WINDOW = 3.0

#: The clip that started this, fetched by id and kept *out* of the threshold
#: choice. Section 7 of the brief: prove the gate rejects it, do not let it
#: pick the number.
KNOWN_UNREADABLE = "37239365"


#: The held-out set. Every query here is new again: the calibration run
#: above spent its own, and a pile that decided a rule cannot also grade it.
HOLDOUT_PILES: tuple[Pile, ...] = (
    Pile("raw apple with skin", "red apples resting on a windowsill", "raw", True, "manzana"),
    Pile("apples in bulk", "boxes of apples at a farmers market", "raw", True, "manzana"),
    Pile("peeled apple", "peeled apple pieces in a bowl of water", "peeled", False, "manzana"),
    Pile("apple dessert", "baked apple strudel dusted with sugar", "dessert", False, "manzana"),
    Pile("strawberries", "strawberries scattered on a linen cloth", "raw", True, "fresas"),
    Pile("strawberry dessert", "strawberry cheesecake slice on a plate", "processed", False, "fresas"),
    Pile("raspberries", "raspberries in a small glass jar", "raw", True, "frambuesas"),
    Pile("kiwi", "kiwi cut into rounds beside a knife", "raw", True, "kiwi"),
    Pile("kiwi in a mixed platter", "tropical fruit buffet with dragon fruit", "mixed", False, "kiwi"),
    Pile("whole avocado", "a heap of avocados in a crate", "whole", True, "aguacate"),
    Pile("halved avocado", "avocado split in two on a dark plate", "halved", True, "aguacate"),
    Pile("sliced avocado", "fanned avocado slices beside bread", "sliced", True, "aguacate"),
    Pile("guacamole", "mashed guacamole being stirred in a bowl", "guacamole", False, "aguacate"),
    Pile("avocado smoothie", "blended green smoothie poured from a jug", "smoothie", False, "aguacate"),
    Pile("food with an animal", "cat lying beside a fruit basket", "animal", False, "fresas"),
)


#: Which piles each command searches. Named once so three things cannot
#: disagree: the freeze check, the runner, and the list of commands the CLI
#: offers - a command the freeze check has never heard of is a command with
#: no freeze check.
PILES_FOR: dict[str, tuple[Pile, ...]] = {
    "berries": BERRY_PILES,
    "entity": ENTITY_PILES,
    "presentation": PRESENTATION_PILES,
    "avocado": AVOCADO_PILES,
    "apple": APPLE_PILES,
    "apple-state": APPLE_STATE_PILES,
    "apple-holdout": APPLE_HOLDOUT_PILES,
    "apple-final": APPLE_FINAL_PILES,
    "sharpness": SHARPNESS_PILES,
    # Pictures for windows already measured. It searches no provider, so it
    # spends no query and has no pile of its own to freeze.
    "strips": (),
    # Focus measures on those same windows. Also searchless.
    "focus": (),
    "holdout": HOLDOUT_PILES,
}


def spent_piles(command: str, burned: set[str]) -> list[Pile]:
    """The piles this command would search that are already used up.

    A pile is spent the moment its numbers decide something or grade
    something: re-running it measures the pile rather than the probe, which
    is the whole failure this file exists to prevent. Checked for the command
    about to run and not for every command there is, because a calibration
    pile is *supposed* to be in the burned list once it has been spent.
    """

    return [p for p in PILES_FOR.get(command, ())
            if p.query.strip().lower() in burned]



# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def collect(providers: Sequence[Any], downloader: Any, pile: Pile, limit: int,
            excluded: set[str], edge: int, frames: int,
            wide: bool = False) -> list[tuple[Any, list[Any], list[Any]]]:
    """Download and decode ``limit`` unseen clips for one pile.

    Returns (clip, frames at the model's input, frames at twice it). The
    second set is what a centre crop is worth measuring on: cropping a frame
    that was already squashed to 224 recovers nothing.
    """

    found: list[Any] = []
    for provider in providers:
        try:
            found.extend(provider.search(pile.query, per_page=limit * 3, page=pile.page))
        except Exception as exc:                           # pragma: no cover
            log.warning("search failed for %r: %s", pile.query, exc)
    taken: list[tuple[Any, list[Any], list[Any]]] = []
    skipped = 0
    for clip in found:
        if len(taken) >= limit:
            break
        if clip.key in excluded:
            skipped += 1
            continue
        got = downloader.fetch_many([clip], needed=1)
        if not got:
            continue
        result = got[0]
        stills = list(getattr(result.clip, "preview_images", None) or [])
        single = getattr(result.clip, "preview_image", "")
        if single and single not in stills:
            stills.append(single)
        source = result.clip.local_path or result.path
        duration = float(getattr(result.clip, "duration", 0.0) or 0.0)
        normal = sample_frames(video=source, stills=stills, duration=duration,
                               count=frames, size=(edge, edge))
        if not normal:
            continue
        big = sample_frames(video=source, stills=stills, duration=duration,
                            count=frames, size=(edge * 2, edge * 2)) if wide else []
        taken.append((result.clip, normal, big))
    if skipped:
        log.info("%s: skipped %d development clip(s)", pile.name, skipped)
    log.info("%s: %d fresh clips for %r", pile.name, len(taken), pile.query)
    return taken


def argmax_label(analyzer: Any, frames: Sequence[Any],
                 labels: dict[str, tuple[str, ...]]) -> tuple[str, dict[str, float]]:
    """Which label group wins the most frames? A confusion matrix needs no cut."""

    names = list(labels)
    prompts = [p for name in names for p in labels[name]]
    spans: list[tuple[int, int]] = []
    at = 0
    for name in names:
        spans.append((at, at + len(labels[name])))
        at += len(labels[name])
    rows = analyzer.probe_frames(frames, prompts, use_claim_model=True)
    if not rows:
        return "", {}
    votes = {name: 0 for name in names}
    for row in rows:
        best = max(range(len(names)), key=lambda i: max(row[spans[i][0]:spans[i][1]]))
        votes[names[best]] += 1
    total = sum(votes.values()) or 1
    return max(votes, key=lambda n: votes[n]), {n: v / total for n, v in votes.items()}


def matrix(rows: Sequence[dict[str, Any]], labels: Sequence[str]) -> dict[str, Any]:
    """truth -> predicted counts, plus precision and recall per label."""

    table = {t: {p: 0 for p in labels} for t in labels}
    for row in rows:
        if row["truth"] in table and row["predicted"] in table[row["truth"]]:
            table[row["truth"]][row["predicted"]] += 1
    scores = {}
    for label in labels:
        tp = table[label][label]
        predicted = sum(table[t][label] for t in labels)
        actual = sum(table[label].values())
        scores[label] = {
            "precision": round(tp / predicted, 3) if predicted else None,
            "recall": round(tp / actual, 3) if actual else None,
            "support": actual,
        }
    return {"matrix": table, "per_label": scores}


# ---------------------------------------------------------------------------
# berries
# ---------------------------------------------------------------------------

def run_berries(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    edge = analyzer.decode_size[0]
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded,
                             edge, 3, wide=True) for p in BERRY_PILES}

    variants = {
        "shipped (3 frames, no crop)": (BERRY_LABELS, False),
        "shipped + centre crop": (BERRY_LABELS, True),
        "arrangement (3 frames, no crop)": (BERRY_CANDIDATE, False),
        "arrangement + centre crop": (BERRY_CANDIDATE, True),
    }
    report: dict[str, Any] = {"command": "berries", "clips_per_pile": args.clips,
                              "variants": {}}
    for title, (labels, crop) in variants.items():
        rows: list[dict[str, Any]] = []
        for pile in BERRY_PILES:
            for clip, normal, big in piles[pile.name]:
                frames = ([crop_center(f, 0.5, (edge, edge)) for f in big]
                          if crop and big else normal)
                predicted, share = argmax_label(analyzer, frames, labels)
                if not predicted:
                    continue
                rows.append({"pile": pile.name, "source": clip.key,
                             "truth": pile.truth, "predicted": predicted,
                             "share": {k: round(v, 2) for k, v in share.items()}})
        confusion = matrix(rows, list(labels))
        correct = sum(1 for r in rows if r["truth"] == r["predicted"])
        report["variants"][title] = {
            **confusion,
            "accuracy": round(correct / len(rows), 3) if rows else None,
            "clips": len(rows),
            "per_clip": rows,
        }
        log.info("%s: accuracy %s over %d clips", title,
                 report["variants"][title]["accuracy"], len(rows))

    # And the production question, which is not the same as the matrix: does
    # a frambuesas beat accept raspberry footage and reject the rest?
    entity = BY_NAME["frambuesas"]
    prompts = [*entity.positives, *entity.competitors]
    gate: dict[str, Any] = {}
    for pile in BERRY_PILES:
        kept = 0
        counted = 0
        for _clip, normal, _big in piles[pile.name]:
            per_frame = analyzer.probe_frames(normal, prompts, use_claim_model=True)
            if not per_frame:
                continue
            counted += 1
            kept += bool(identify_food(entity, per_frame).passed)
        gate[pile.name] = f"{kept}/{counted}"
    report["frambuesas_gate_shipped"] = gate
    log.info("frambuesas gate, shipped prompts: %s", gate)
    return report


# ---------------------------------------------------------------------------
# avocado
# ---------------------------------------------------------------------------

#: The candidate rules. The shipped one is first so the table reads as a
#: before/after, and every candidate is written from the *question* rather
#: than from the clips that embarrassed the last one: a beat that says
#: "aguacate" wants the fruit visible, in any cut, and does not want a drink.
AVOCADO_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "shipped": {
        "required": ("a fresh raw avocado",
                     "an avocado cut in half showing the stone",
                     "sliced green avocado flesh"),
        "forbidden": ("a tub of packaged guacamole dip", "an avocado smoothie"),
    },
    "fruit-is-visible": {
        "required": ("a whole avocado with dark green skin",
                     "an avocado cut in half showing the stone",
                     "slices of green avocado flesh",
                     "avocado on toast with visible slices"),
        "forbidden": ("a green drink in a glass",
                      "a smooth green dip with no visible fruit",
                      "a bowl of mashed green paste"),
    },
    "fruit-is-visible-strict": {
        "required": ("a whole avocado with dark green skin",
                     "an avocado cut in half showing the stone",
                     "slices of green avocado flesh"),
        "forbidden": ("a green drink in a glass",
                      "a smooth green dip with no visible fruit",
                      "a bowl of mashed green paste",
                      "green vegetables that are not avocado"),
    },
}


def run_avocado(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    edge = analyzer.decode_size[0]
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded, edge, 3)
             for p in AVOCADO_PILES}
    report: dict[str, Any] = {"command": "avocado", "rules": {}}

    for name, rule in AVOCADO_RULES.items():
        prompts = [*rule["required"], *rule["forbidden"]]
        positives = len(rule["required"])
        per_pile: dict[str, Any] = {}
        for pile in AVOCADO_PILES:
            accepted = counted = 0
            losers: dict[str, int] = {}
            for _clip, frames, _big in piles[pile.name]:
                rows = analyzer.probe_frames(frames, prompts, use_claim_model=True)
                if not rows:
                    continue
                counted += 1
                wins = 0
                for row in rows:
                    best = max(range(len(prompts)), key=lambda i: row[i])
                    if best < positives:
                        wins += 1
                    else:
                        loser = prompts[best]
                        losers[loser] = losers.get(loser, 0) + 1
                if wins / len(rows) >= 0.5:
                    accepted += 1
            per_pile[pile.name] = {
                "state": pile.truth,
                "should_accept": pile.accept,
                "accepted": f"{accepted}/{counted}",
                "accepted_pct": round(100.0 * accepted / counted, 1) if counted else None,
                "top_forbidden": max(losers, key=lambda k: losers[k]) if losers else "",
            }
        good = [p for p in AVOCADO_PILES if p.accept]
        bad = [p for p in AVOCADO_PILES if not p.accept]

        def total(piles_: Sequence[Pile], key: int) -> int:
            return sum(int(per_pile[p.name]["accepted"].split("/")[key]) for p in piles_)

        report["rules"][name] = {
            "required": list(rule["required"]),
            "forbidden": list(rule["forbidden"]),
            "per_pile": per_pile,
            "accepted_of_valid": f"{total(good, 0)}/{total(good, 1)}",
            "accepted_of_invalid": f"{total(bad, 0)}/{total(bad, 1)}",
        }
        log.info("avocado %s: valid %s, invalid %s", name,
                 report["rules"][name]["accepted_of_valid"],
                 report["rules"][name]["accepted_of_invalid"])
    return report


# ---------------------------------------------------------------------------
# presentation - does the context prompt describe the food or the crockery
# ---------------------------------------------------------------------------

def _rates(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    """Precision, recall and both error rates for one verdict column."""

    good = [r for r in rows if r["should_accept"]]
    bad = [r for r in rows if not r["should_accept"]]
    tp = sum(1 for r in good if r[key])
    fp = sum(1 for r in bad if r[key])
    return {
        "accepted_of_valid": f"{tp}/{len(good)}",
        "accepted_of_invalid": f"{fp}/{len(bad)}",
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "recall": round(tp / len(good), 3) if good else None,
        "false_negative_rate": round(100.0 * (len(good) - tp) / len(good), 1) if good else None,
        "false_positive_rate": round(100.0 * fp / len(bad), 1) if bad else None,
    }


def run_presentation(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """Is a valid strawberry still a strawberry when it is not in a bowl?

    Two questions at once, because they are answered by the same frames. The
    **entity probe alone** is where the third benchmark said most of the
    recall went, and the **whole conjunction** is what actually gates a beat;
    reporting one without the other is what made "the conjunction is too
    strict" look true when it was not.

    The piles hold the food constant and vary the presentation - bowl, plate,
    linen, board, supermarket box, a hand - and the rejections that must
    survive the rewrite are in here too, because a context prompt that stops
    naming the crockery must not also stop rejecting the dessert.
    """

    edge = analyzer.decode_size[0]
    clips = {p.name: collect(providers, downloader, p, args.clips, excluded, edge, 3)
             for p in PRESENTATION_PILES}

    report: dict[str, Any] = {"command": "presentation", "variants": {}}
    for title, spec in CONTEXT_CANDIDATES.items():
        overrides = spec["context"]
        wrong = spec["wrong"] or WRONG_CONTEXT
        rows: list[dict[str, Any]] = []
        for pile in PRESENTATION_PILES:
            entity = BY_NAME[pile.food]
            requirement = requirement_for_food(entity)
            if overrides and pile.food in overrides:
                requirement = replace(
                    requirement,
                    context_requirements=tuple(overrides[pile.food]),
                )
            prompts, _ = requirement_prompts(requirement, wrong)
            for clip, frames, _big in clips[pile.name]:
                matrix = analyzer.probe_frames(frames, prompts, use_claim_model=True)
                if not matrix:
                    continue
                full = score_requirement(requirement, matrix, wrong)
                alone = identify_food(
                    entity,
                    [row[:len(entity.positives) + len(entity.competitors)]
                     for row in matrix],
                )
                rows.append({
                    "pile": pile.name, "food": pile.food,
                    "presentation": pile.truth, "source": clip.key,
                    "should_accept": pile.accept,
                    "entity_alone": bool(alone.passed),
                    "conjunction": bool(full.passed),
                    "context_score": (round(full.context_match_score, 3)
                                      if full.context_checked else None),
                    "failed_on": list(full.failed_on),
                })
        per_food = {
            food: {
                "entity_alone": _rates([r for r in rows if r["food"] == food],
                                       "entity_alone"),
                "conjunction": _rates([r for r in rows if r["food"] == food],
                                      "conjunction"),
            }
            for food in sorted({r["food"] for r in rows})
        }
        per_presentation = {}
        for shape in sorted({r["presentation"] for r in rows}):
            subset = [r for r in rows if r["presentation"] == shape]
            per_presentation[shape] = {
                "clips": len(subset),
                "should_accept": subset[0]["should_accept"],
                "entity_alone": sum(1 for r in subset if r["entity_alone"]),
                "conjunction": sum(1 for r in subset if r["conjunction"]),
            }
        report["variants"][title] = {
            "context_overrides": overrides or "shipped",
            "wrong_context": list(wrong),
            "clips": len(rows),
            "entity_alone": _rates(rows, "entity_alone"),
            "conjunction": _rates(rows, "conjunction"),
            "per_food": per_food,
            "per_presentation": per_presentation,
            "per_clip": rows,
        }
        log.info("%s: entity alone %s, conjunction %s", title,
                 report["variants"][title]["entity_alone"]["recall"],
                 report["variants"][title]["conjunction"]["recall"])
    return report


# ---------------------------------------------------------------------------
# entity - can the probe see the fruit it is looking for at all
# ---------------------------------------------------------------------------

def run_entity(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """Does the entity probe recognise the fruit in every shape it comes in?

    The layer under everything else, and the one the held-out benchmark
    pointed at: a probe whose positives all describe a cut cannot see a whole
    avocado, and nothing built on top of it can rescue that.

    Scored exactly as production scores it - the identification probe against
    the food's own competitors - so what changes between variants is the
    wording and nothing else.
    """

    edge = analyzer.decode_size[0]
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded, edge, 3)
             for p in ENTITY_PILES}
    report: dict[str, Any] = {"command": "entity", "foods": {}}

    for food, variants in ENTITY_CANDIDATES.items():
        entity = BY_NAME[food]
        mine = [p for p in ENTITY_PILES if p.food == food]
        rows: dict[str, Any] = {}
        for name, positives in variants.items():
            candidate = replace(entity, positives=tuple(positives))
            prompts = [*candidate.positives, *candidate.competitors]
            per_pile: dict[str, Any] = {}
            kept = counted = leaked = wrong = 0
            for pile in mine:
                accepted = seen = 0
                losers: dict[str, int] = {}
                for _clip, frames, _big in piles[pile.name]:
                    matrix = analyzer.probe_frames(frames, prompts,
                                                   use_claim_model=True)
                    if not matrix:
                        continue
                    seen += 1
                    verdict = identify_food(candidate, matrix)
                    accepted += bool(verdict.passed)
                    if verdict.top_distractor:
                        losers[verdict.top_distractor] = (
                            losers.get(verdict.top_distractor, 0) + 1)
                per_pile[pile.name] = {
                    "should_accept": pile.accept,
                    "accepted": f"{accepted}/{seen}",
                    "top_competitor": (max(losers, key=lambda k: losers[k])
                                       if losers else ""),
                }
                if pile.accept:
                    kept += accepted
                    counted += seen
                else:
                    leaked += accepted
                    wrong += seen
            rows[name] = {
                "positives": list(positives),
                "per_pile": per_pile,
                "kept_of_valid": f"{kept}/{counted}",
                "accepted_of_invalid": f"{leaked}/{wrong}",
            }
            log.info("%s / %s: valid %s, invalid %s", food, name,
                     rows[name]["kept_of_valid"], rows[name]["accepted_of_invalid"])
        report["foods"][food] = {"competitors": list(entity.competitors),
                                 "variants": rows}
    return report


# ---------------------------------------------------------------------------
# sharpness - is this window readable, not just correct
# ---------------------------------------------------------------------------

def strip_of(video: str, positions: Sequence[float], target: Path,
             height: int = 640, quality: int = 4) -> bool:
    """One JPEG showing the whole window: its three sampled moments, in order.

    A single midpoint frame would hide the half of a window that goes soft,
    and the label being asked for is about the window rather than about an
    instant. The three positions are exactly the ones ``window_quality``
    measured, so the picture and the number describe the same thing.
    """

    target.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    for at in positions:
        inputs += ["-ss", f"{max(0.0, float(at)):.3f}", "-i", str(video)]
    count = len(positions)
    chain = "".join(
        f"[{i}:v]scale=-2:{height},setsar=1[v{i}];" for i in range(count)
    ) + "".join(f"[v{i}]" for i in range(count)) + f"hstack=inputs={count}[out]"
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-nostdin",
        *inputs, "-filter_complex", chain, "-map", "[out]",
        "-frames:v", "1", "-q:v", str(int(quality)), str(target),
    ]
    subprocess.run(command, check=False, timeout=120)
    return target.exists() and target.stat().st_size > 0


def emit_strip(name: str, path: Path, note: str) -> None:
    """Put the picture in the log, because the artifact store is unreachable.

    The same encoding ``tools/inspect_reel_frames.py`` uses, and read back the
    same way: blob storage answers 403 from this network, so a frame that
    only exists in an artifact is a frame nobody can look at.
    """

    if not path.exists():
        print(f"::warning::no strip for {name}")
        return
    blob = base64.b64encode(path.read_bytes()).decode("ascii")
    print(f"FRAME-BEGIN {name} at=0.0s bytes={path.stat().st_size}")
    print(f"FRAME-TEXT {name} {note}")
    for index in range(0, len(blob), 200):
        print(f"FRAME-DATA {name} {blob[index:index + 200]}")
    print(f"FRAME-END {name}")


def pexels_clip_by_id(video_id: str) -> Any | None:
    """One known Pexels video, by id rather than by search.

    ``pexels:37239365`` is the clip the readability gate has to reject, and a
    search cannot be relied on to return one specific video. Its windows are
    measured and reported and are deliberately excluded from choosing the
    threshold - a rule fitted to the example that motivated it fits nothing
    else.
    """

    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return None
    try:
        from vidfactory.http import request_json
        from vidfactory.stock.pexels import PexelsProvider

        payload = request_json(
            f"https://api.pexels.com/videos/videos/{video_id}",
            headers={"Authorization": key}, timeout=30.0,
        )
        clips = PexelsProvider.parse({"videos": [payload]}, "known unreadable")
        return clips[0] if clips else None
    except Exception as exc:                               # pragma: no cover
        log.warning("could not fetch pexels:%s: %s", video_id, exc)
        return None


def measure_windows(analyzer, clip, video: str, seconds: float, requirement,
                    work: Path, label: str) -> list[dict[str, Any]]:
    """Every window of one source: its numbers, and a picture of it."""

    rows: list[dict[str, Any]] = []
    # Three windows a clip, not every window a clip offers. Each one has to
    # be looked at by a person to earn its label, and a set nobody finishes
    # reading is a set that decides nothing.
    starts = window_starts(seconds, SHARPNESS_WINDOW)
    if len(starts) > 3:
        starts = [starts[0], starts[len(starts) // 2], starts[-1]]
    for index, start in enumerate(starts):
        positions = segment_positions(start, SHARPNESS_WINDOW, 3)
        frames = segment_frames(
            video, start, SHARPNESS_WINDOW, 3, analyzer.decode_size
        )
        if not frames:
            continue
        quality = window_quality(frames)
        grounding = ground_requirement(analyzer, frames, requirement)
        window_id = f"{clip.key}@{start:.2f}"
        name = f"{label}-{index:02d}"
        row = {
            "window_id": window_id,
            "strip": name,
            "food": requirement.required_entity,
            "source": clip.key,
            "provider": clip.provider,
            "source_start": round(start, 3),
            "source_end": round(start + SHARPNESS_WINDOW, 3),
            "source_seconds": round(seconds, 2),
            "sampled_at": positions,
            "window_sharpness": quality["sharpness"],
            "window_centre_weight": quality["centre_weight"],
            "window_steadiness": quality["steadiness"],
            "window_quality": quality["quality"],
            "segment_grounding_score": round(grounding.score, 3),
            "segment_grounding_passed": bool(grounding.passed),
            "failed_on": list(grounding.failed_on),
        }
        rows.append(row)
        strip = work / f"{name}.jpg"
        if strip_of(video, positions, strip):
            emit_strip(name, strip, (
                f"{window_id} food={row['food']} "
                f"sharp={row['window_sharpness']:.3f} "
                f"centre={row['window_centre_weight']:.3f} "
                f"steady={row['window_steadiness']:.3f} "
                f"quality={row['window_quality']:.3f} "
                f"grounding={row['segment_grounding_score']:.2f}"
                f"{'' if row['segment_grounding_passed'] else ' FAILED'}"
            ))
    return rows


WINDOWS_FILE = Path("data/calibration/window_readability_windows.json")

#: How many strips one run may emit. The job-log API returns at most about
#: 828 KB however many lines are asked for, and the first ``sharpness`` run
#: emitted ninety-two strips across 78,517 lines - the numbers survived
#: because they print last, and eighty-eight of the pictures were cut off the
#: front. A calibration whose evidence cannot be looked at is not one.
STRIP_BUDGET = 33


def stratified(rows: Sequence[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """A spread across the sharpness range rather than the first ``count``.

    One threshold is being placed on one axis, so the windows worth looking
    at are the ones spanning that axis - including both ends, which is where
    "obviously fine" and "obviously unusable" have to be confirmed rather
    than assumed.
    """

    ordered = sorted(rows, key=lambda r: float(r.get("window_sharpness", 0.0)))
    if len(ordered) <= count:
        return ordered
    step = (len(ordered) - 1) / (count - 1)
    picked = {int(round(i * step)) for i in range(count)}
    return [ordered[i] for i in sorted(picked)]


def run_strips(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """Re-emit the pictures for windows already measured, small enough to read.

    Nothing is re-measured: the numbers come from
    ``window_readability_windows.json`` and the sources are fetched by id, so
    the strip shown is the window scored. Only the picture is new, and only
    because the first run's pictures did not survive the log.
    """

    if not WINDOWS_FILE.exists():
        print(f"no measured windows at {WINDOWS_FILE}")
        return {"command": "strips", "windows": 0}
    data = json.loads(WINDOWS_FILE.read_text(encoding="utf-8"))
    rows = list(data.get("per_window") or [])
    known = list((data.get("known_unreadable") or {}).get("per_window") or [])

    # The known clip is always shown - it is the case the gate has to reject
    # and a reviewer has to see it - and it never counts towards the floor.
    # A band of the sharpness axis rather than the whole of it. The first
    # strips run emitted thirty-three and the log delivered eighteen - the
    # sharpest, because they print last - so the low end where the floor
    # actually sits arrived as nothing at all. Asking for one band at a time
    # is how the evidence fits through.
    # Named windows take precedence over the band. Expanding a labelled set
    # means drawing the specific windows a decision is short of, not a fresh
    # spread across an axis that has already been read.
    wanted = [w.strip() for w in
              str(getattr(args, "window_ids", "") or "").split(",") if w.strip()]
    if wanted:
        by_id = {str(r.get("window_id")): r for r in rows + known}
        by_strip = {str(r.get("strip")): r for r in rows + known}
        chosen = [by_id.get(w) or by_strip.get(w) for w in wanted]
        missing = [w for w, r in zip(wanted, chosen) if r is None]
        if missing:
            log.warning("no measured window for %s", ", ".join(missing))
        chosen = [r for r in chosen if r is not None]
    else:
        low = float(getattr(args, "sharpness_min", 0.0) or 0.0)
        high = getattr(args, "sharpness_max", None)
        high = float(high) if high is not None else 1.0
        banded = [r for r in rows
                  if low <= float(r.get("window_sharpness", 0.0)) <= high]
        chosen = stratified(banded, max(1, STRIP_BUDGET - len(known))) + known
    work = Path("output/holdout/strips")
    work.mkdir(parents=True, exist_ok=True)

    sources: dict[str, str] = {}
    emitted: list[dict[str, Any]] = []
    for row in chosen:
        key = str(row.get("source", ""))
        if key not in sources:
            clip = pexels_clip_by_id(key.split(":", 1)[-1])
            got = downloader.fetch_many([clip], needed=1) if clip is not None else []
            sources[key] = str(got[0].clip.local_path or got[0].path) if got else ""
        video = sources[key]
        if not video:
            log.warning("could not fetch %s", key)
            continue
        name = str(row.get("strip") or row.get("window_id"))
        strip = work / f"{name}.jpg"
        if strip_of(video, list(row.get("sampled_at") or []), strip,
                    height=int(getattr(args, "strip_height", 240) or 240),
                    quality=int(getattr(args, "strip_quality", 4) or 4)):
            emit_strip(name, strip, (
                f"{row.get('window_id')} food={row.get('food')} "
                f"sharp={float(row.get('window_sharpness', 0)):.3f} "
                f"centre={float(row.get('window_centre_weight', 0)):.3f} "
                f"steady={float(row.get('window_steadiness', 0)):.3f} "
                f"quality={float(row.get('window_quality', 0)):.3f} "
                f"grounding={float(row.get('segment_grounding_score', 0)):.2f}"
                f"{'' if row.get('segment_grounding_passed') else ' GROUNDING-FAILED'}"
            ))
            emitted.append({"strip": name, "window_id": row.get("window_id")})
    return {
        "command": "strips",
        "windows": len(emitted),
        "budget": STRIP_BUDGET,
        "note": (
            "Pictures only. The numbers are in "
            "data/calibration/window_readability_windows.json and nothing here "
            "re-measures them."
        ),
        "emitted": emitted,
    }


LABELS_FILE = Path("data/calibration/window_readability_labels.json")

#: Where focus is measured. Production decodes to the claim model's 224x224,
#: which squashes a 16:9 frame and lowpasses away most of the evidence blur
#: leaves behind - a downsample is itself a sharpening operation. So the
#: candidates are measured at both sizes, and whether the resolution is
#: itself part of the answer is one of the things being asked.
FOCUS_SIZES: tuple[tuple[str, tuple[int, int]], ...] = (
    ("224 (what production sees)", (224, 224)),
    ("480x270 (native aspect)", (480, 270)),
)


def run_focus(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """Local focus measures on the windows already measured and already labelled.

    No search, no new footage: the sources are fetched by provider id and the
    frames are the same ``sampled_at`` positions ``window_quality`` used, so
    every number here describes a window that already has a hand-made label
    beside it.

    Nothing is thresholded. This prints distributions; whether any candidate
    separates is read off them afterwards, and the file says so.
    """

    if not WINDOWS_FILE.exists():
        print(f"no measured windows at {WINDOWS_FILE}")
        return {"command": "focus", "windows": 0}
    data = json.loads(WINDOWS_FILE.read_text(encoding="utf-8"))
    rows = list(data.get("per_window") or [])
    known = list((data.get("known_unreadable") or {}).get("per_window") or [])
    labels = {}
    if LABELS_FILE.exists():
        for row in json.loads(LABELS_FILE.read_text(encoding="utf-8"))["labels"]:
            labels[row["window_id"]] = row["label"]

    sources: dict[str, str] = {}
    measured: list[dict[str, Any]] = []
    for row in rows + known:
        key = str(row.get("source", ""))
        if key not in sources:
            clip = pexels_clip_by_id(key.split(":", 1)[-1])
            got = downloader.fetch_many([clip], needed=1) if clip is not None else []
            sources[key] = str(got[0].clip.local_path or got[0].path) if got else ""
        video = sources[key]
        if not video:
            log.warning("could not fetch %s", key)
            continue

        out: dict[str, Any] = {
            "window_id": row.get("window_id"),
            "strip": row.get("strip"),
            "food": row.get("food"),
            "source": key,
            "label": labels.get(str(row.get("window_id")), ""),
            "held_out": row in known,
            "window_sharpness": row.get("window_sharpness"),
            "window_centre_weight": row.get("window_centre_weight"),
            "segment_grounding_score": row.get("segment_grounding_score"),
            "segment_grounding_passed": row.get("segment_grounding_passed"),
        }
        positions = list(row.get("sampled_at") or [])
        for title, size in FOCUS_SIZES:
            frames = [f for f in (
                decode_frame(video, at, size, 30.0) for at in positions
            ) if f is not None and f.ok]
            if not frames:
                continue
            stats = [focus_statistics(f) for f in frames]
            # The weakest frame of the window, not the average of them: a
            # window is only as watchable as its worst moment, which is the
            # same rule the grounding conjunction uses.
            for name in stats[0]:
                out[f"{name}@{title.split()[0]}"] = round(
                    min(s[name] for s in stats), 5)
            out[f"edge_density@{title.split()[0]}"] = round(
                min(measure(f).edge_density for f in frames), 3)
        measured.append(out)
        log.info("%s (%s): lap224=%s lap480=%s",
                 out["window_id"], out["label"] or "unlabelled",
                 out.get("laplacian_variance@224"),
                 out.get("laplacian_variance@480x270"))

    return {
        "command": "focus",
        "windows": len(measured),
        "labelled": sum(1 for r in measured if r["label"]),
        "sizes": [t for t, _s in FOCUS_SIZES],
        "note": (
            "No threshold is chosen here and none is applied anywhere. Each "
            "window carries the weakest of its three frames, because a window "
            "is only as watchable as its worst moment."
        ),
        "per_window": measured,
    }


def run_sharpness(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """Measure every window, show every window, decide nothing.

    This command does not pick a threshold. It produces the numbers and the
    pictures they describe, and a person reads the pictures - which is the
    only way a label like "a viewer can see what this is" gets attached to a
    window at all. The floor is chosen afterwards, from the labels, in
    ``data/calibration/window_readability_labels.json``.
    """

    edge = analyzer.decode_size[0]
    work = Path("output/holdout/strips")
    work.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for pile in SHARPNESS_PILES:
        entity = BY_NAME[pile.food]
        requirement = requirement_for_food(entity)
        for order, (clip, _frames, _big) in enumerate(
            collect(providers, downloader, pile, args.clips, excluded, edge, 1)
        ):
            video = getattr(clip, "local_path", "") or ""
            seconds = float(getattr(clip, "duration", 0.0) or 0.0)
            if not video or seconds <= 0.5:
                continue
            label = f"{pile.food}-{pile.name.split()[-1]}-{order:02d}"
            rows.extend(measure_windows(
                analyzer, clip, video, seconds, requirement, work, label
            ))

    # The known failure, measured beside the rest and excluded from the
    # decision. Fetched by id because a search will not reliably return one
    # specific video.
    known: list[dict[str, Any]] = []
    clip = pexels_clip_by_id(KNOWN_UNREADABLE)
    if clip is not None:
        got = downloader.fetch_many([clip], needed=1)
        if got:
            result = got[0]
            video = result.clip.local_path or result.path
            seconds = float(getattr(result.clip, "duration", 0.0) or 0.0)
            known = measure_windows(
                analyzer, result.clip, str(video), seconds,
                requirement_for_food(BY_NAME["manzana"]), work, "known-manzana",
            )
    else:
        log.warning("pexels:%s could not be fetched", KNOWN_UNREADABLE)

    return {
        "command": "sharpness",
        "window_seconds": SHARPNESS_WINDOW,
        "windows": len(rows),
        "note": (
            "No threshold is chosen here. Every window carries its numbers and "
            "a three-frame strip in the log; the labels live in "
            "data/calibration/window_readability_labels.json and the floor is "
            "read off those."
        ),
        "per_window": rows,
        "known_unreadable": {
            "source": f"pexels:{KNOWN_UNREADABLE}",
            "why": (
                "shipped in run 34331777135 at segment grounding 1.00 over a "
                "blurred hand; excluded from choosing the floor"
            ),
            "per_window": known,
        },
    }


# ---------------------------------------------------------------------------
# apple-state - which wording of "con piel" keeps a real apple
# ---------------------------------------------------------------------------

def _union_probe(analyzer, frames, requirements: Sequence[Any],
                 wrong: Sequence[str]) -> tuple[dict[str, int], list[list[float]]]:
    """One encode of the frames against every prompt any variant needs.

    Seven state wordings share their entity, context and dominance prompts and
    differ in a handful of columns, so encoding the images seven times would
    pay 0.55 s a frame to compute the same numbers again. The frames are
    encoded once against the union, and each variant reads its own columns
    back out - identical arithmetic, a seventh of the runtime.
    """

    order: dict[str, int] = {}
    for requirement in requirements:
        for prompt in requirement_prompts(requirement, wrong)[0]:
            order.setdefault(prompt, len(order))
    return order, analyzer.probe_frames(frames, list(order), use_claim_model=True)


def _as_variant(order: dict[str, int], master: Sequence[Sequence[float]],
                requirement: Any, wrong: Sequence[str]) -> list[list[float]]:
    """The union matrix cut down to the columns one variant asks for."""

    prompts, _ = requirement_prompts(requirement, wrong)
    columns = [order[p] for p in prompts]
    return [[row[i] for i in columns] for row in master]


def _per_class(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    """Accepted of seen, per presentation class, which is what the brief asks."""

    out: dict[str, Any] = {}
    for shape in sorted({r["presentation"] for r in rows}):
        subset = [r for r in rows if r["presentation"] == shape]
        out[shape] = {
            "should_accept": subset[0]["should_accept"],
            "accepted": f"{sum(1 for r in subset if r[key])}/{len(subset)}",
        }
    return out


def _blamed(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Which probe threw away each piece of valid footage, counted.

    ``lost_on`` is the union across a whole variant, so a run in which the
    state probe rejects everything and the context probe rejects one clip
    reads exactly like a run in which they share the work. This counts, and
    counts per class, because "the state wording is wrong" and "the context
    prompts reject a single apple" have different fixes and the first
    calibration could not tell them apart.
    """

    lost = [r for r in rows if r["should_accept"] and not r["conjunction"]]
    counts: dict[str, int] = {}
    per_class: dict[str, dict[str, int]] = {}
    for row in lost:
        for probe in row["failed_on"]:
            counts[probe] = counts.get(probe, 0) + 1
            per_class.setdefault(row["presentation"], {})
            per_class[row["presentation"]][probe] = (
                per_class[row["presentation"]].get(probe, 0) + 1)
    return {
        "valid_clips_lost": len(lost),
        "by_probe": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "by_class": per_class,
    }


def run_apple_state(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """Which wording of "manzana con piel" keeps the apples that are apples?

    The presentation run measured ``manzana`` at entity recall 0.800 and
    conjunction recall 0.400 at precision 1.000, so half the valid apple
    footage dies between the entity probe and the state probe - and the state
    probe asks for apples *on a tree*. That is a fact about the scene and the
    requirement is a fact about the fruit.

    Every variant is scored on the same frames, and the entity probe's own
    verdict is reported beside them, because a clip the entity probe already
    rejected is not evidence about any state wording.
    """

    entity = BY_NAME["manzana"]
    shipped = requirement_for_food(entity)
    variants = {
        name: replace(shipped,
                      required_attributes=tuple(spec["required"]),
                      forbidden_attributes=tuple(spec["forbidden"]))
        for name, spec in APPLE_STATE_CANDIDATES.items()
    }
    edge = analyzer.decode_size[0]
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded, edge, 3)
             for p in APPLE_STATE_PILES}

    per_variant: dict[str, list[dict[str, Any]]] = {name: [] for name in variants}
    entity_rows: list[dict[str, Any]] = []
    for pile in APPLE_STATE_PILES:
        for clip, frames, _big in piles[pile.name]:
            order, master = _union_probe(analyzer, frames, variants.values(),
                                         WRONG_CONTEXT)
            if not master:
                continue
            width = len(entity.positives) + len(entity.competitors)
            alone = identify_food(entity, [row[:width] for row in master])
            entity_rows.append({
                "pile": pile.name, "presentation": pile.truth,
                "source": clip.key, "should_accept": pile.accept,
                "entity_alone": bool(alone.passed),
                "looked_like": alone.top_distractor,
            })
            for name, requirement in variants.items():
                verdict = score_requirement(
                    requirement, _as_variant(order, master, requirement, WRONG_CONTEXT),
                    WRONG_CONTEXT,
                )
                per_variant[name].append({
                    "pile": pile.name, "presentation": pile.truth,
                    "source": clip.key, "should_accept": pile.accept,
                    "entity_alone": bool(alone.passed),
                    "conjunction": bool(verdict.passed),
                    "state_score": round(verdict.state_match_score, 3),
                    "failed_on": list(verdict.failed_on),
                })

    def accepted(rows: Sequence[dict[str, Any]], shape: str) -> int:
        return sum(1 for r in rows if r["presentation"] == shape and r["conjunction"])

    report: dict[str, Any] = {
        "command": "apple-state",
        "clips": len(entity_rows),
        # The floor under every variant. A wording cannot rescue a clip the
        # entity probe threw away, so this is the ceiling on all of them.
        "entity_alone": _rates(entity_rows, "entity_alone"),
        "entity_per_class": _per_class(entity_rows, "entity_alone"),
        "variants": {},
    }
    for name, rows in per_variant.items():
        spec = APPLE_STATE_CANDIDATES[name]
        lost = [r for r in rows
                if r["should_accept"] and r["entity_alone"] and not r["conjunction"]]
        report["variants"][name] = {
            "required": list(spec["required"]),
            "forbidden": list(spec["forbidden"]),
            "conjunction": _rates(rows, "conjunction"),
            "per_class": _per_class(rows, "conjunction"),
            # The brief's success conditions, counted rather than described.
            "oranges_accepted": accepted(rows, "orange"),
            "dessert_accepted": accepted(rows, "dessert"),
            "peeled_accepted": accepted(rows, "peeled"),
            "juice_accepted": accepted(rows, "juice"),
            # Valid footage the entity probe kept and this wording then threw
            # away: the cost of the state layer, isolated from everything
            # underneath it.
            "lost_after_entity": len(lost),
            "lost_on": sorted({p for r in lost for p in r["failed_on"]}),
            # Which probe did the rejecting, counted rather than unioned.
            "blamed": _blamed(rows),
            "per_clip": rows,
        }
        log.info("%s: recall %s, precision %s, oranges %d, dessert %d, peeled %d",
                 name, report["variants"][name]["conjunction"]["recall"],
                 report["variants"][name]["conjunction"]["precision"],
                 report["variants"][name]["oranges_accepted"],
                 report["variants"][name]["dessert_accepted"],
                 report["variants"][name]["peeled_accepted"])
    report["per_clip"] = entity_rows
    return report


def run_apple_final(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """One named change, on a third apple set, and then this stops.

    Not a calibration: two wordings, one of them the one that ships, and the
    other differing from it by a single negative prompt that two independent
    measurements have already blamed. The accept rule is the brief's own and
    is written down before the numbers arrive - precision at or above 0.95,
    no peeled apple accepted, no apple dessert accepted, no orange accepted,
    and a material improvement in recall. Anything less and the wording that
    ships keeps shipping.
    """

    entity = BY_NAME["manzana"]
    base = requirement_for_food(entity)
    variants = {
        name: replace(base,
                      required_attributes=tuple(spec["required"]),
                      forbidden_attributes=tuple(spec["forbidden"]))
        for name, spec in APPLE_FINAL_CANDIDATES.items()
    }
    edge = analyzer.decode_size[0]
    width = len(entity.positives) + len(entity.competitors)

    per_variant: dict[str, list[dict[str, Any]]] = {name: [] for name in variants}
    entity_rows: list[dict[str, Any]] = []
    for pile in APPLE_FINAL_PILES:
        for clip, frames, _big in collect(providers, downloader, pile, args.clips,
                                          excluded, edge, 3):
            order, master = _union_probe(analyzer, frames, variants.values(),
                                         WRONG_CONTEXT)
            if not master:
                continue
            alone = identify_food(entity, [row[:width] for row in master])
            entity_rows.append({
                "pile": pile.name, "presentation": pile.truth,
                "source": clip.key, "should_accept": pile.accept,
                "entity_alone": bool(alone.passed),
            })
            for name, requirement in variants.items():
                verdict = score_requirement(
                    requirement, _as_variant(order, master, requirement, WRONG_CONTEXT),
                    WRONG_CONTEXT,
                )
                per_variant[name].append({
                    "pile": pile.name, "presentation": pile.truth,
                    "source": clip.key, "should_accept": pile.accept,
                    "conjunction": bool(verdict.passed),
                    "state_score": round(verdict.state_match_score, 3),
                    "failed_on": list(verdict.failed_on),
                    "looked_like": verdict.top_distractor,
                })

    report: dict[str, Any] = {
        "command": "apple-final",
        "clips": len(entity_rows),
        "accept_rule": (
            "precision >= 0.95, peeled 0, dessert 0, orange 0, and recall "
            "materially above the shipped wording - written before the run"
        ),
        "entity_alone": _rates(entity_rows, "entity_alone"),
        "entity_per_class": _per_class(entity_rows, "entity_alone"),
        "variants": {},
    }
    for name, rows in per_variant.items():
        def seen(shape: str) -> int:
            return sum(1 for r in rows
                       if r["presentation"] == shape and r["conjunction"])
        report["variants"][name] = {
            "required": list(APPLE_FINAL_CANDIDATES[name]["required"]),
            "forbidden": list(APPLE_FINAL_CANDIDATES[name]["forbidden"]),
            "conjunction": _rates(rows, "conjunction"),
            "per_class": _per_class(rows, "conjunction"),
            "blamed": _blamed(rows),
            "oranges_accepted": seen("orange"),
            "dessert_accepted": seen("dessert"),
            "peeled_accepted": seen("peeled"),
            "juice_accepted": seen("juice"),
            "false_positives": [
                {"pile": r["pile"], "source": r["source"],
                 "state_score": r["state_score"]}
                for r in rows if not r["should_accept"] and r["conjunction"]
            ],
            "per_clip": rows,
        }
        log.info("%s: precision %s, recall %s, peeled %d, dessert %d, orange %d",
                 name, report["variants"][name]["conjunction"]["precision"],
                 report["variants"][name]["conjunction"]["recall"],
                 report["variants"][name]["peeled_accepted"],
                 report["variants"][name]["dessert_accepted"],
                 report["variants"][name]["oranges_accepted"])
    report["per_clip"] = entity_rows
    return report


def run_apple_holdout(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    """The applied apple wording, on apple footage nothing has been tuned on.

    Whatever ``foods.py`` says at the moment this runs - no variants, no
    overrides. The calibration above chose a wording and this grades it, and
    the two cannot be the same clips or the grade means nothing.
    """

    requirement = requirement_for_food(BY_NAME["manzana"])
    entity = requirement.entity
    prompts, _ = requirement_prompts(requirement, WRONG_CONTEXT)
    width = len(entity.positives) + len(entity.competitors)
    edge = analyzer.decode_size[0]

    rows: list[dict[str, Any]] = []
    for pile in APPLE_HOLDOUT_PILES:
        for clip, frames, _big in collect(providers, downloader, pile, args.clips,
                                          excluded, edge, 3):
            matrix = analyzer.probe_frames(frames, prompts, use_claim_model=True)
            if not matrix:
                continue
            verdict = score_requirement(requirement, matrix, WRONG_CONTEXT)
            alone = identify_food(entity, [row[:width] for row in matrix])
            rows.append({
                "pile": pile.name, "presentation": pile.truth,
                "source": clip.key, "should_accept": pile.accept,
                "entity_alone": bool(alone.passed),
                "conjunction": bool(verdict.passed),
                "state_score": round(verdict.state_match_score, 3),
                "failed_on": list(verdict.failed_on),
                "looked_like": verdict.top_distractor,
            })

    report = {
        "command": "apple-holdout",
        "clips": len(rows),
        "state_required": list(requirement.required_attributes),
        "state_forbidden": list(requirement.forbidden_attributes),
        "entity_alone": _rates(rows, "entity_alone"),
        "conjunction": _rates(rows, "conjunction"),
        "entity_per_class": _per_class(rows, "entity_alone"),
        "per_class": _per_class(rows, "conjunction"),
        "blamed": _blamed(rows),
        "oranges_accepted": sum(1 for r in rows
                                if r["presentation"] == "orange" and r["conjunction"]),
        "dessert_accepted": sum(1 for r in rows
                                if r["presentation"] == "dessert" and r["conjunction"]),
        "peeled_accepted": sum(1 for r in rows
                               if r["presentation"] == "peeled" and r["conjunction"]),
        "false_negatives": [
            {"pile": r["pile"], "source": r["source"], "failed_on": r["failed_on"],
             "looked_like": r["looked_like"]}
            for r in rows if r["should_accept"] and not r["conjunction"]
        ],
        "false_positives": [
            {"pile": r["pile"], "source": r["source"], "state_score": r["state_score"]}
            for r in rows if not r["should_accept"] and r["conjunction"]
        ],
        "per_clip": rows,
    }
    log.info("held out: entity recall %s, conjunction recall %s, precision %s",
             report["entity_alone"]["recall"], report["conjunction"]["recall"],
             report["conjunction"]["precision"])
    return report


# ---------------------------------------------------------------------------
# apple - backends and formulations together
# ---------------------------------------------------------------------------

#: Every backend worth trying on a free runner, with why it is a candidate.
#: ``licence`` is the model's, and it is a selection criterion rather than a
#: footnote: this is a commercial channel.
BACKENDS: tuple[dict[str, Any], ...] = (
    {
        "name": "clip-vit-large-patch14 (quantized, in production)",
        "repo": "Xenova/clip-vit-large-patch14",
        "vision_file": "onnx/vision_model_quantized.onnx",
        "text_file": "onnx/text_model_quantized.onnx",
        "image_size": 224,
        "licence": "MIT (OpenAI CLIP weights, MIT)",
    },
    {
        "name": "clip-vit-large-patch14 (full precision)",
        "repo": "Xenova/clip-vit-large-patch14",
        "vision_file": "onnx/vision_model.onnx",
        "text_file": "onnx/text_model.onnx",
        "image_size": 224,
        "licence": "MIT (OpenAI CLIP weights, MIT)",
    },
    {
        "name": "siglip-base-patch16-224",
        "repo": "Xenova/siglip-base-patch16-224",
        "vision_file": "onnx/vision_model_quantized.onnx",
        "text_file": "onnx/text_model_quantized.onnx",
        "image_size": 224,
        "licence": "Apache-2.0",
    },
)

#: Three ways of asking the same question, because the formulation may be the
#: whole problem. The shipped one asks about *absence*, which is what a
#: contrastive model is worst at; the others put a positive on both sides.
APPLE_FORMULATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "absence (shipped)": {
        "required": ("a fresh raw apple with its skin on", "a whole unpeeled apple",
                     "raw apple slices with the red skin still on"),
        "forbidden": ("a peeled apple with no skin", "a slice of apple cake",
                      "apple pie", "a glass of apple juice",
                      "cooked apple or apple sauce",
                      "a processed apple dessert with cream"),
    },
    "positive-vs-positive": {
        "required": ("a red apple with shiny red skin",
                     "a green apple with smooth green skin",
                     "an apple whose red skin covers it"),
        "forbidden": ("a pale yellow apple with the skin cut away",
                      "white apple flesh with no colour on the outside",
                      "a brown baked apple dessert",
                      "a glass of cloudy apple juice"),
    },
    "colour-and-surface": {
        "required": ("apples with glossy red and green surfaces",
                     "apples on a tree with their skin on"),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
}


def peak_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def run_apple(args, _analyzer, providers, downloader, excluded, config) -> dict[str, Any]:
    """Which backend, if any, can see an apple's skin - and what does it cost?

    The frames are decoded once at the largest input any candidate wants and
    re-used, so what is timed is the model rather than FFmpeg.
    """

    biggest = max(int(b["image_size"]) for b in BACKENDS)
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded,
                             biggest, 3) for p in APPLE_PILES}

    report: dict[str, Any] = {"command": "apple", "backends": []}
    for spec in BACKENDS:
        entry = {k: v for k, v in spec.items() if k != "name"}
        entry["name"] = spec["name"]
        before = peak_mb()
        started = time.time()
        try:
            settings = {"enabled": True, "repo": spec["repo"],
                        "vision_file": spec["vision_file"],
                        "text_file": spec["text_file"],
                        "tokenizer_file": "tokenizer.json",
                        "image_size": spec["image_size"], "fallback": False,
                        "threads": int(config.get("visual.claim_model.threads", 2))}
            model = load_model(settings)
        except Exception as exc:                           # pragma: no cover
            model = None
            entry["error"] = str(exc)[:300]
        entry["load_seconds"] = round(time.time() - started, 1)
        if model is None:
            entry["loaded"] = False
            entry.setdefault("error", "load_model returned None")
            report["backends"].append(entry)
            log.warning("%s did not load: %s", spec["name"], entry["error"])
            continue

        entry["loaded"] = True
        probe = VisualAnalyzer(model=model, claim_model=model, frames_per_clip=3,
                               allow_remote_video=False)
        edge = probe.decode_size[0]
        entry["image_size"] = edge
        formulations: dict[str, Any] = {}
        frame_count = 0
        spent = 0.0
        for title, rule in APPLE_FORMULATIONS.items():
            prompts = [*rule["required"], *rule["forbidden"]]
            positives = len(rule["required"])
            per_pile: dict[str, str] = {}
            correct = total = 0
            for pile in APPLE_PILES:
                accepted = counted = 0
                for _clip, frames, _big in piles[pile.name]:
                    usable = [crop_center(f, 1.0, (edge, edge)) for f in frames]
                    started = time.time()
                    rows = probe.probe_frames(usable, prompts, use_claim_model=True)
                    spent += time.time() - started
                    frame_count += len(usable)
                    if not rows:
                        continue
                    counted += 1
                    wins = sum(
                        1 for row in rows
                        if max(range(len(prompts)), key=lambda i: row[i]) < positives
                    )
                    accepted += (wins / len(rows)) >= 0.5
                per_pile[pile.name] = f"{accepted}/{counted}"
                correct += accepted if pile.accept else counted - accepted
                total += counted
            formulations[title] = {
                "per_pile": per_pile,
                "accuracy": round(correct / total, 3) if total else None,
            }
            log.info("%s / %s: accuracy %s", spec["name"], title,
                     formulations[title]["accuracy"])
        entry["formulations"] = formulations
        entry["seconds_per_frame"] = round(spent / frame_count, 3) if frame_count else None
        entry["peak_rss_mb"] = round(peak_mb(), 1)
        entry["rss_added_mb"] = round(peak_mb() - before, 1)
        report["backends"].append(entry)
        del probe, model
    return report


# ---------------------------------------------------------------------------
# holdout - the whole gate, on unseen footage
# ---------------------------------------------------------------------------

def run_holdout(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    edge = analyzer.decode_size[0]
    rows: list[dict[str, Any]] = []
    for pile in HOLDOUT_PILES:
        entity = BY_NAME[pile.food]
        requirement = requirement_for_food(entity)
        prompts, _ = requirement_prompts(requirement)
        for clip, frames, _big in collect(providers, downloader, pile, args.clips,
                                          excluded, edge, 3):
            per_frame = analyzer.probe_frames(frames, prompts, use_claim_model=True)
            if not per_frame:
                continue
            full = score_requirement(requirement, per_frame)
            entity_only = identify_food(
                entity,
                [row[:len(entity.positives) + len(entity.competitors)]
                 for row in per_frame],
            )
            rows.append({
                "pile": pile.name, "food": pile.food, "state": pile.truth,
                "source": clip.key, "should_accept": pile.accept,
                "accepted_before": bool(entity_only.passed),
                "accepted_after": bool(full.passed),
                "entity_score": round(full.entity_presence_score, 3),
                "state_score": round(full.state_match_score, 3) if full.state_checked else None,
                "context_score": round(full.context_match_score, 3) if full.context_checked else None,
                "dominant_subject_score": round(full.dominant_subject_score, 3),
                "failed_on": list(full.failed_on),
                "looked_like": full.top_distractor,
            })
            log.info("%s %s: before %s after %s%s", pile.name, clip.key,
                     "accept" if entity_only.passed else "reject",
                     "accept" if full.passed else "reject",
                     "" if full.passed else f" ({','.join(full.failed_on)})")

    def rates(key: str, subset: Sequence[dict[str, Any]]) -> dict[str, Any]:
        good = [r for r in subset if r["should_accept"]]
        bad = [r for r in subset if not r["should_accept"]]
        tp = sum(1 for r in good if r[key])
        fp = sum(1 for r in bad if r[key])
        fn = len(good) - tp
        return {
            "accepted_of_valid": f"{tp}/{len(good)}",
            "accepted_of_invalid": f"{fp}/{len(bad)}",
            "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
            "recall": round(tp / len(good), 3) if good else None,
            "false_negative_rate": round(100.0 * fn / len(good), 1) if good else None,
            "false_positive_rate": round(100.0 * fp / len(bad), 1) if bad else None,
        }

    by_food: dict[str, Any] = {}
    for food in sorted({r["food"] for r in rows}):
        subset = [r for r in rows if r["food"] == food]
        by_food[food] = {"before": rates("accepted_before", subset),
                         "after": rates("accepted_after", subset)}
    by_state: dict[str, Any] = {}
    for state in sorted({r["state"] for r in rows}):
        subset = [r for r in rows if r["state"] == state]
        by_state[state] = {
            "clips": len(subset),
            "should_accept": subset[0]["should_accept"],
            "accepted_before": sum(1 for r in subset if r["accepted_before"]),
            "accepted_after": sum(1 for r in subset if r["accepted_after"]),
        }
    return {
        "command": "holdout",
        "clips": len(rows),
        "before": rates("accepted_before", rows),
        "after": rates("accepted_after", rows),
        "per_food": by_food,
        "per_state": by_state,
        "per_clip": rows,
    }


# ---------------------------------------------------------------------------

#: Keys whose value is a long list of individual clips. Useful in the
#: artifact, fatal in a log.
BULKY = ("per_clip", "own_scores", "wrong_scores")


def without_rows(value: Any) -> Any:
    """The report with its per-clip arrays replaced by their length."""

    if isinstance(value, dict):
        return {
            k: (f"<{len(v)} rows, in the artifact>"
                if k in BULKY and isinstance(v, list) else without_rows(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [without_rows(v) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(PILES_FOR))
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--clips", type=int, default=6)
    parser.add_argument("--out", default="")
    # Which slice of the sharpness axis to draw, and how big. The log hands
    # back about 828 KB however much is printed, so a run that draws
    # everything at full size delivers only whatever printed last.
    parser.add_argument("--sharpness-min", type=float, default=0.0)
    parser.add_argument("--sharpness-max", type=float, default=1.0)
    parser.add_argument("--strip-height", type=int, default=240)
    parser.add_argument("--strip-quality", type=int, default=4)
    #: Draw exactly these windows, by window_id or by strip name. Overrides
    #: the band: expanding a labelled set is about specific windows.
    parser.add_argument("--window-ids", default="")
    args = parser.parse_args(argv)
    setup_logging(verbose=False)

    config = load_config(args.config)
    providers = build_providers(dict(config.get("sources", {}) or {}))
    if not providers:
        print("no stock provider is available")
        return 2
    excluded, burned = frozen()
    log.info("excluding %d development clips and %d spent queries",
             len(excluded), len(burned))
    already = spent_piles(args.command, burned)
    if already:
        print("these piles have already been spent, on deciding a rule or on "
              "grading one, and cannot do either again:")
        for pile in already:
            print(f"  {pile.name}: {pile.query!r}")
        print("write new queries for this command before running it.")
        return 2

    downloader = ClipDownloader(
        workdir=Path("work/holdout"), min_width=1280, min_height=720,
        min_seconds=2.0, max_mb=90, timeout=120, retries=2,
    )

    if args.command == "apple":
        report = run_apple(args, None, providers, downloader, excluded, config)
    else:
        settings = dict(config.get("visual.claim_model", {}) or {})
        settings.setdefault("enabled", True)
        model = load_model(settings)
        if model is None:
            print("no claim model; nothing to measure")
            return 2
        analyzer = VisualAnalyzer(model=model, claim_model=model,
                                  frames_per_clip=3, allow_remote_video=False)
        runner = {"berries": run_berries, "entity": run_entity,
                  "presentation": run_presentation,
                  "avocado": run_avocado, "holdout": run_holdout,
                  "apple-state": run_apple_state,
                  "apple-holdout": run_apple_holdout,
                  "apple-final": run_apple_final,
                  "sharpness": run_sharpness,
                  "strips": run_strips,
                  "focus": run_focus}[args.command]
        report = runner(args, analyzer, providers, downloader, excluded)

    report["held_out_from"] = {"clips": len(excluded), "queries": sorted(burned)}
    target = Path(args.out or f"output/holdout/{args.command}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # The file keeps everything; the log gets the summary. A per-clip dump of
    # ninety-eight clips across three variants pushed the aggregates past the
    # end of what GitHub will hand back from a job log, which is a measurement
    # taken and then lost.
    print(json.dumps(without_rows(report), indent=2))
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
