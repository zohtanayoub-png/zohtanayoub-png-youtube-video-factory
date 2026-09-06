"""The frame has to demonstrate the advice, not contain its noun.

Run 44 is the whole argument for this module. It reported

    entity_grounding_failure_count   = 0
    entity_grounding_pass_percentage = 100%

across 93 grounded shots, and put a dragonfly on a windowpane under "do not
block the window", a kitchen faucet under the same advice, and colourful
metallic ribbons under "paint the trim the same colour as the walls". None of
those is a scoring error. Every one of them contains the object the sentence
is about, and nothing else displaces it, which is the only question
:mod:`vidfactory.entities` asks.

These tests pin the second question - is the *claim* demonstrated - and pin
just as carefully what it is not allowed to become: a claim is required only
where the narration makes one, one frame does not decide a clip, and an
uninspected shot is not a failure.
"""

from __future__ import annotations

import pytest

from vidfactory.entities import BY_NAME as ENTITIES_BY_NAME
from vidfactory.instructions import (
    CLAIMS,
    CLAIM_DOMINANCE_FAIL,
    InstructionClaim,
    InstructionGrounding,
    claim_prompts,
    repair_queries,
    required_claim,
    score_from_similarities,
    summarise,
)
from vidfactory.visual_analysis import _ramp


def _claim(name: str) -> InstructionClaim:
    return next(c for c in CLAIMS if c.name == name)


def _frames(claim, positive: float, forbidden: float, count: int = 3):
    """Similarity rows shaped like the ones the model returns."""

    return [
        [positive] * len(claim.positives) + [forbidden] * len(claim.forbidden)
        for _ in range(count)
    ]


# ---------------------------------------------------------------------------
# Which shots make a claim at all
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("narration, expected", [
    ("Keep anything above windowsill height away from the window wall", "window_layout"),
    ("This one is simple: do not block the window", "window_layout"),
    ("Then: paint the trim the same color as the walls", "wall_trim_paint"),
    ("Aim for a rug wide enough that the front legs of every seat sit on it",
     "rug_sizing"),
    ("Aim for at least three light sources per room", "layered_lighting"),
    ("Light the room from the perimeter with lamps", "layered_lighting"),
])
def test_the_narration_declares_its_claim(narration, expected):
    claim = required_claim(narration)
    assert claim is not None and claim.name == expected


@pytest.mark.parametrize("narration", [
    "Balance visual weight across the room",
    "Edit down what is on show until every surface has room to breathe",
    "Measure the room before you buy anything",
    "",
])
def test_abstract_advice_claims_nothing(narration):
    """Demanding a scene the sentence never promised rejects good footage.

    The same rule the entity layer follows, for the same reason: this is an
    additional gate on shots that make a visual claim, not a new floor under
    every shot in the video.
    """

    assert required_claim(narration) is None


def test_a_passing_mention_does_not_move_the_claim():
    """The claim named first, like the entity named first.

    "Keep the sofa clear of the window" is window-layout advice that mentions
    a sofa; it is not seating advice.
    """

    claim = required_claim(
        "Keep tall furniture away from the window so the light reaches the sofa"
    )
    assert claim is not None and claim.name == "window_layout"


def test_every_claim_names_an_entity_the_other_layer_knows():
    """The two layers have to agree about the subject, not argue about it."""

    for claim in CLAIMS:
        assert claim.entity in ENTITIES_BY_NAME, claim.name
        assert claim.observed_failures, (
            f"{claim.name} has no observed failure to measure itself against"
        )


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------

def test_a_frame_that_shows_the_relationship_passes():
    window = _claim("window_layout")
    result = score_from_similarities(window, _frames(window, 0.30, 0.24), _ramp)
    assert result.checked and result.passed and not result.failed
    assert result.score > CLAIM_DOMINANCE_FAIL


def test_a_dragonfly_on_a_windowpane_is_rejected():
    """Run 44, tip 9, verbatim.

    The frame contains a window - the entity layer is right about that and
    passes it. What it does not contain is a room whose furniture is clear of
    the window, and the forbidden prompt naming the insect beats every
    statement of the claim.
    """

    window = _claim("window_layout")
    insect = window.forbidden.index("a close-up of an insect resting on a windowpane")
    per_frame = [
        [0.20] * len(window.positives)
        + [0.20 + (0.14 if i == insect else 0.0) for i in range(len(window.forbidden))]
        for _ in range(3)
    ]
    result = score_from_similarities(window, per_frame, _ramp)
    assert result.failed
    assert result.top_forbidden == "a close-up of an insect resting on a windowpane"
    assert "does not show" in result.detail


def test_ribbons_under_paint_the_trim_are_rejected():
    """Run 44, tip 14, verbatim - and run 25's failure before it.

    The entity layer's three trim distractors pulled ``wall_finish`` down to a
    median of 0.669 on this render and rejected nothing, because a painted
    ornamental surface genuinely is a painted surface. The claim names what
    the advice actually needs: a wall, and trim on it, in a room.
    """

    trim = _claim("wall_trim_paint")
    ribbons = trim.forbidden.index("colourful metallic ribbons and party streamers")
    per_frame = [
        [0.19] * len(trim.positives)
        + [0.19 + (0.16 if i == ribbons else 0.01) for i in range(len(trim.forbidden))]
        for _ in range(3)
    ]
    assert score_from_similarities(trim, per_frame, _ramp).failed


def test_a_room_that_merely_also_contains_the_forbidden_thing_is_kept():
    """A living room can hold a plant on the sill and still show the advice.

    A margin, not a presence test - the same lesson two entity calibration
    runs paid for.
    """

    window = _claim("window_layout")
    assert score_from_similarities(window, _frames(window, 0.26, 0.25), _ramp).passed


def test_one_bad_frame_does_not_condemn_a_clip_that_shows_the_advice():
    window = _claim("window_layout")
    per_frame = (
        _frames(window, 0.30, 0.24, count=2) + _frames(window, 0.18, 0.34, count=1)
    )
    assert score_from_similarities(window, per_frame, _ramp).passed


def test_one_lucky_frame_does_not_rescue_a_clip_that_does_not():
    window = _claim("window_layout")
    per_frame = (
        _frames(window, 0.18, 0.34, count=2) + _frames(window, 0.31, 0.22, count=1)
    )
    assert not score_from_similarities(window, per_frame, _ramp).passed


def test_an_uninspected_shot_is_not_a_failure():
    grounding = InstructionGrounding(claim="window_layout", label="x")
    assert grounding.required and not grounding.checked and not grounding.failed
    assert grounding.to_dict()["instruction_grounding_passed"] is True


def test_the_prompts_are_positives_then_forbidden():
    for claim in CLAIMS:
        prompts, offset = claim_prompts(claim)
        assert offset == len(claim.positives)
        assert prompts[offset:] == list(claim.forbidden)
        assert len(set(prompts)) == len(prompts), claim.name


# ---------------------------------------------------------------------------
# What the two layers each catch
# ---------------------------------------------------------------------------

def test_entity_grounding_passing_does_not_answer_the_instruction():
    """The exact shape of run 44, as the pipeline sees it.

    A shot with a passing entity score, a passing relevance score and a failed
    claim is still a weak shot. Neither of the first two numbers is allowed to
    answer the third - the same rule entity grounding was given against
    semantic similarity, one layer up.
    """

    visual = {
        "analyzed": True,
        "semantic_match": 0.71,
        "entity": "window",
        "entity_grounding_checked": True,
        "entity_grounding_passed": True,
        "required_visual_claim": "window_layout",
        "instruction_grounding_checked": True,
        "instruction_grounding_passed": False,
        "instruction_grounding_score": 0.12,
    }
    assert visual["semantic_match"] > 0.5
    assert visual["entity_grounding_passed"]
    assert not visual["instruction_grounding_passed"]

    summary = summarise([visual])
    assert summary["failed"] == 1
    assert summary["pass_percentage"] == 0.0


def test_repair_searches_for_the_relationship_not_the_object():
    """Searching for the object is what returned the dragonfly."""

    queries = repair_queries("Keep tall furniture away from the window wall")
    assert queries
    assert any("living room" in q for q in queries)
    assert not any(q.strip() == "window" for q in queries)


def test_abstract_advice_keeps_its_own_query():
    assert repair_queries("Balance visual weight", "balanced living room") == [
        "balanced living room"
    ]


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def _rows(failures: int, total: int = 6):
    rows = []
    for index in range(total):
        bad = index < failures
        rows.append({
            "required_visual_claim": "window_layout",
            "instruction_label": "furniture kept clear of the window",
            "instruction_grounding_checked": True,
            "instruction_grounding_passed": not bad,
            "instruction_grounding_score": 0.1 if bad else 0.9,
            "instruction_grounding_detail": "x",
            "instruction_top_forbidden": "a kitchen sink and tap in front of a window",
        })
    return rows


def test_the_report_counts_only_measured_failures():
    summary = summarise(_rows(2))
    assert summary["checked"] == 6 and summary["failed"] == 2
    assert summary["pass_percentage"] == round(100.0 * 4 / 6, 1)
    assert summary["by_claim"]["window_layout"]["failed"] == 2
    assert summary["by_claim"]["window_layout"]["closest_forbidden"]


def test_nothing_inspected_reports_a_clean_pass_rather_than_a_failure():
    summary = summarise([{"required_visual_claim": "window_layout"}])
    assert summary["checked"] == 0 and summary["failed"] == 0
    assert summary["pass_percentage"] == 100.0


@pytest.mark.parametrize("mode, failures, should_pass", [
    ("test", 0, True),
    ("test", 1, True),         # tolerated, and reported as a warning
    ("test", 2, False),
    ("production", 0, True),
    ("production", 1, False),  # absolute
])
def test_the_instruction_gate_splits_by_mode(mode, failures, should_pass):
    """The same split the entity gate has, for the same reason.

    A claim is a harder thing to see than an object, so if anything this
    probe's false-positive rate is the higher of the two - and a published
    video is still the thing all of this exists to protect.
    """

    summary = summarise(_rows(failures))
    limit = 0 if mode == "production" else 1
    assert (summary["failed"] <= limit) is should_pass
