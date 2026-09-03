"""The frame has to be about the thing the sentence is about.

Run 25 passed every relevance gate the pipeline had - a 0.569 average over the
clips on screen and not one below the 0.50 floor - and put colourful ribbons
under "paint the trim the same colour as the walls" and potted plants under
"a rug too small to reach the sofa".

Two calibration runs over real Pexels footage narrowed what this can honestly
claim. Certifying that an object is *present* separates nothing: a living room
photograph contains a wall, a floor, a window and a sofa at once, so the answer
is nearly always yes and the measurement is noise. Being *displaced* - a frame
that plants or ribbons clearly own - is a different question, and it is the one
the run 25 failures actually were.

These tests pin that rule, and the two editorial rules from the same run: a
causal sentence has to explain its own section's idea, and may not rest on one
of the section's optional examples.
"""

from __future__ import annotations

import pytest

from vidfactory.causal_alignment import CAUSAL_CONNECTIVES
from vidfactory.entities import (
    ENTITIES,
    ENTITY_DOMINANCE_FAIL,
    EntityGrounding,
    entities_in,
    repair_queries,
    required_entity,
    required_labels,
    score_from_similarities,
    summarise,
)
from vidfactory.principles import (
    condition_sentence,
    find_optional_example_leakage,
    find_principle_contamination,
    primary_principle,
)
from vidfactory.visual_analysis import _ramp


# ---------------------------------------------------------------------------
# What the advice requires
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "narration, expected",
    [
        ("A rug too small to reach the sofa leaves the seating floating", "rug"),
        ("Choose a rug large enough for the front legs", "rug"),
        ("Paint the trim the same color as the walls", "wall_finish"),
        ("Hang the curtains high and wide beside the window", "window_dressing"),
        ("Hang art at eye level and scale it to the furniture", "wall_art"),
        ("Put a large mirror opposite the window", "mirror"),
        ("Pull the sofa away from the wall", "seating"),
        ("Add a floor lamp to light the darkest corner", "lighting"),
        ("Let the daylight through the window reach the far wall", "window"),
        ("Stand one tall plant in the empty corner", "greenery"),
    ],
)
def test_concrete_advice_names_the_object_it_needs(narration, expected):
    entity = required_entity(narration)
    assert entity is not None and entity.name == expected


def test_the_subject_is_the_object_named_first_not_the_one_named_most():
    """The sofa is the landmark; the rug is the advice.

    "A rug too small to reach the sofa leaves the seating floating" names
    seating twice and the rug once. Requiring a sofa here would have accepted
    the sofa-without-a-rug shots that run 25 actually shipped.
    """

    assert required_labels("A rug too small to reach the sofa leaves the "
                           "seating floating")[0] == "rug"


@pytest.mark.parametrize("narration", [
    "Balance visual weight across the room",
    "Edit down what is on show",
    "Keep the palette narrow and let the room breathe",
])
def test_abstract_advice_requires_no_object(narration):
    """Demanding an object a sentence never promised rejects good footage."""

    assert required_entity(narration) is None
    assert required_labels(narration) == []


def test_every_entity_offers_positives_competitors_and_its_own_queries():
    for entity in ENTITIES:
        assert entity.positives and entity.competitors and entity.queries
        assert entity.labels
        # A competitor that is also a positive would make the margin
        # meaningless, and one shared prompt is enough to do it.
        assert not set(entity.positives) & set(entity.competitors)


# ---------------------------------------------------------------------------
# The contrastive measurement
# ---------------------------------------------------------------------------

def _entity(name: str):
    return next(e for e in ENTITIES if e.name == name)


def _frames(entity, positive: float, competitor: float, count: int = 3):
    """Similarity rows shaped like the ones the model returns."""

    return [
        [positive] * len(entity.positives) + [competitor] * len(entity.competitors)
        for _ in range(count)
    ]


def test_a_clip_where_the_object_holds_the_frame_is_grounded():
    rug = _entity("rug")
    result = score_from_similarities(rug, _frames(rug, 0.30, 0.24), _ramp)
    assert result.checked and result.passed
    assert result.score > ENTITY_DOMINANCE_FAIL
    assert not result.failed


def test_a_room_that_merely_also_contains_other_things_is_not_rejected():
    """A real living room holds a wall, a floor, a window and a sofa at once.

    Two calibration runs said so with numbers: asking "is the object present"
    of interior footage separates nothing, because the answer is nearly always
    yes. Only a shot that something else clearly owns is a failure.
    """

    rug = _entity("rug")
    assert score_from_similarities(rug, _frames(rug, 0.26, 0.25), _ramp).passed


def test_a_frame_something_else_owns_is_rejected():
    """The point of the module: sentence similarity cannot see this.

    Every competitor beats every rug prompt by a clear margin, which is what a
    frame of plants under rug narration looks like - and it still scores well
    against the sentence, because the sentence and the room share a whole
    vocabulary.
    """

    rug = _entity("rug")
    result = score_from_similarities(rug, _frames(rug, 0.22, 0.29), _ramp)
    assert result.checked and not result.passed and result.failed
    assert "something else" in result.detail


def test_plants_under_rug_narration_are_rejected():
    """Run 25 at 8:35, verbatim: rug advice, potted plants on screen."""

    rug = _entity("rug")
    assert required_entity("A rug too small to reach the sofa").name == "rug"
    # "indoor potted plants" is one of the competitors, so a plant clip lands
    # on it far harder than on any of the rug prompts.
    per_frame = [
        [0.19, 0.20, 0.18, 0.19] + [0.21, 0.34, 0.22, 0.20, 0.19]
        for _ in range(3)
    ]
    result = score_from_similarities(rug, per_frame, _ramp)
    assert result.failed


def test_one_bad_frame_does_not_condemn_a_clip_that_shows_the_object():
    """The median, for the same reason the pixel flags use one."""

    rug = _entity("rug")
    per_frame = _frames(rug, 0.30, 0.24, count=2) + _frames(rug, 0.20, 0.32, count=1)
    assert score_from_similarities(rug, per_frame, _ramp).passed


def test_one_lucky_frame_does_not_rescue_a_clip_that_does_not():
    rug = _entity("rug")
    per_frame = _frames(rug, 0.20, 0.32, count=2) + _frames(rug, 0.31, 0.22, count=1)
    assert not score_from_similarities(rug, per_frame, _ramp).passed


def test_an_unchecked_shot_is_not_a_failure():
    """No model, no frames, no verdict - which is not the same as a bad one."""

    grounding = EntityGrounding(entity="rug", labels=("rug",))
    assert grounding.required and not grounding.checked and not grounding.failed
    assert grounding.to_dict()["entity_grounding_passed"] is True


def test_a_high_generic_score_cannot_compensate_for_a_missing_object():
    """The rule the user asked for, stated as the pipeline sees it.

    A clip carrying a 0.72 semantic match and a failed grounding is still a
    weak shot; nothing about the first number is allowed to answer the second.
    """

    visual = {
        "analyzed": True,
        "semantic_match": 0.72,
        **EntityGrounding(
            entity="rug", labels=("rug",), checked=True, score=0.18, passed=False
        ).to_dict(),
    }
    ungrounded = bool(
        visual.get("entity")
        and visual.get("entity_grounding_checked")
        and not visual.get("entity_grounding_passed")
    )
    assert ungrounded


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

def test_repair_searches_for_the_object_not_for_the_advice():
    queries = repair_queries("a rug too small to reach the sofa", "small living room")
    assert any("rug" in q for q in queries)
    assert "properly sized area rug under sofa" in queries


def test_abstract_advice_keeps_its_own_query():
    assert repair_queries("balance visual weight", "balanced room") == ["balanced room"]


def test_the_report_counts_only_measured_failures():
    rows = [
        {"entity": "rug", "entity_grounding_checked": True, "entity_grounding_passed": False,
         "entity_presence_score": 0.2, "entity_grounding_detail": "no rug visible"},
        {"entity": "rug", "entity_grounding_checked": True, "entity_grounding_passed": True},
        {"entity": "mirror", "entity_grounding_checked": False, "entity_grounding_passed": True},
        {"entity": "", "entity_grounding_checked": False, "entity_grounding_passed": True},
    ]
    summary = summarise(rows)
    assert summary["requiring_an_entity"] == 3
    assert summary["checked"] == 2
    assert summary["failed"] == 1
    assert summary["pass_percentage"] == 50.0


def test_nothing_inspected_reports_a_clean_pass_rather_than_a_failure():
    assert summarise([])["pass_percentage"] == 100.0
    assert summarise([])["failed"] == 0


# ---------------------------------------------------------------------------
# Run 25 idea 15, verbatim
# ---------------------------------------------------------------------------

RUN_25_IDEA_15_HEADING = "Balance visual weight across the room"
RUN_25_IDEA_15 = (
    "Balance visual weight across the room. Spread the taller and darker "
    "pieces so they do not all land on one side. Oversized furniture eats "
    "visible floor area and narrows the walking paths, so the room feels "
    "tighter."
)


def test_run_25_idea_15_is_caught():
    """The report said cross_concept_contamination_count = 0, correctly.

    "Balance visual weight" names no physical thing, so the object-level check
    had no subject to compare against. Balance is about where visual mass
    sits; that sentence is about how much floor a sofa covers.
    """

    assert primary_principle(RUN_25_IDEA_15_HEADING).name == "visual_weight_balance"
    found = find_principle_contamination(
        RUN_25_IDEA_15_HEADING, RUN_25_IDEA_15, connectives=CAUSAL_CONNECTIVES
    )
    assert len(found) == 1
    assert found[0].principle == "visual_weight_balance"
    assert found[0].intruder == "furniture_footprint"
    assert "walking paths" in found[0].sentence


def test_a_real_explanation_of_balance_is_left_alone():
    text = (
        "Balance visual weight across the room. Spread the heavy pieces so "
        "they do not all land on one side, so the eye settles and the room "
        "reads calmer than it measures."
    )
    assert not find_principle_contamination(
        RUN_25_IDEA_15_HEADING, text, connectives=CAUSAL_CONNECTIVES
    )


def test_a_sentence_without_a_connective_is_not_a_causal_claim():
    """Only sentences that claim a consequence are under test."""

    text = "Balance visual weight across the room. Oversized furniture is bulky."
    assert not find_principle_contamination(
        RUN_25_IDEA_15_HEADING, text, connectives=CAUSAL_CONNECTIVES
    )


def test_one_shared_word_is_not_a_foreign_principle():
    """"Floor" turns up in advice about everything; two hits is the bar."""

    text = (
        "Balance visual weight across the room. Keep one side from taking "
        "the whole floor, so the weight reads even."
    )
    assert not find_principle_contamination(
        RUN_25_IDEA_15_HEADING, text, connectives=CAUSAL_CONNECTIVES
    )


# ---------------------------------------------------------------------------
# Run 25 idea 8, verbatim
# ---------------------------------------------------------------------------

RUN_25_IDEA_8_HEADING = "Leave the corners of the room resolved"
RUN_25_IDEA_8 = (
    "Leave the corners of the room resolved. Give each empty corner one "
    "deliberate thing: a plant, a floor lamp, a mirror or a low chair. "
    "A reflection adds depth, so the room reads larger than it measures."
)


def test_run_25_idea_8_leaks_through_one_optional_example():
    """Four options, and the reason covers exactly one of them."""

    found = find_optional_example_leakage(
        RUN_25_IDEA_8_HEADING, RUN_25_IDEA_8, connectives=CAUSAL_CONNECTIVES
    )
    assert len(found) == 1
    assert found[0].used == "mirror"
    assert {"greenery", "lighting", "mirror"} <= set(found[0].options)


def test_conditioning_the_sentence_resolves_the_leak():
    """The reason is true; it just has to say which case it covers."""

    found = find_optional_example_leakage(
        RUN_25_IDEA_8_HEADING, RUN_25_IDEA_8, connectives=CAUSAL_CONNECTIVES
    )
    fixed = RUN_25_IDEA_8.replace(
        found[0].sentence, condition_sentence(found[0].sentence, found[0].used)
    )
    assert fixed.count("If you choose the mirror") == 1
    assert not find_optional_example_leakage(
        RUN_25_IDEA_8_HEADING, fixed, connectives=CAUSAL_CONNECTIVES
    )


def test_an_explanation_covering_the_principle_is_not_leakage():
    text = (
        "Leave the corners of the room resolved. Give each empty corner one "
        "deliberate thing: a plant, a floor lamp, a mirror or a low chair. "
        "A corner with something in it stops reading as dead space, so the "
        "room feels finished rather than unfinished."
    )
    assert not find_optional_example_leakage(
        RUN_25_IDEA_8_HEADING, text, connectives=CAUSAL_CONNECTIVES
    )


def test_a_section_about_one_thing_may_explain_itself_through_it():
    """Mirror advice explaining itself through a reflection is not leakage."""

    text = (
        "Hang a large mirror opposite the window. Choose one that reaches "
        "almost to the ceiling or a wide landscape shape. A reflection adds "
        "depth, so the room reads larger than it measures."
    )
    assert not find_optional_example_leakage(
        "Hang a large mirror opposite the window", text,
        connectives=CAUSAL_CONNECTIVES,
    )


def test_an_enumeration_is_read_as_the_options_it_offers():
    named = entities_in("a plant, a floor lamp, a mirror or a low chair")
    assert {"greenery", "lighting", "mirror", "seating"} <= named
