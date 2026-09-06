"""The four script defects run 44 shipped at a contamination count of zero.

Every paragraph below is the real narration from that render, copied out of a
reproduction of its script rather than invented for the test. All four passed
``cross_concept_contamination_count == 0`` and
``primary_concept_contamination_count == 0``, and all four are wrong:

1. balance advice explained through an oversized sofa's footprint
2. focal-point advice explained through one-large-object-versus-many-small
3. window advice explained through lighting the perimeter with lamps
4. a lighting section conditioned on "if you choose the wall finish"

Each case is pinned twice. The first half asserts the detector sees the
paragraph, because that is what returned zero. The second half asserts the
repair pass can no longer *write* it, because a detector that only reports
after the fact is how three of these survived a rewrite: the vocabulary check
refused one wording of the furniture-footprint explanation and accepted the
next one from the same family.
"""

from __future__ import annotations

import pytest

from vidfactory.causal_alignment import connectives_for
from vidfactory.concepts import find_contamination
from vidfactory.entities import entities_in
from vidfactory.languages import resolve_language
from vidfactory.principles import (
    find_false_conditioning,
    find_optional_example_leakage,
    find_principle_contamination,
    mechanism_fits,
    primary_principle,
)
from vidfactory.script_generator import generate_script
from vidfactory.title_alignment import detect_promise
from vidfactory.topic_engine import TopicEngine

TITLE = "15 Small Living Room Tricks That Make Your Space Look Bigger"


@pytest.fixture(scope="module")
def connectives():
    return connectives_for(detect_promise(TITLE))


# ----------------------------------------------------------------------
# 1. Balance visual weight across the room
# ----------------------------------------------------------------------
BALANCE = (
    "Balance visual weight across the room, and it matters more than it "
    "sounds like it should. If all the heavy, dark, tall pieces end up on one "
    "side, the room feels like it is tipping, even if nobody can name why. "
    "Mentally split the room in half and check that each side carries a "
    "similar amount of mass. Balance a tall bookcase with a heavy sofa, not "
    "with a floor lamp. Oversized furniture eats visible floor area and "
    "narrows the walking paths, so a small room feels cramped even though its "
    "footprint never changed."
)


def test_balance_advice_may_not_be_explained_by_furniture_footprint(connectives):
    heading = "Balance visual weight across the room"
    found = find_principle_contamination(heading, BALANCE, None, connectives=connectives)
    assert found, "the oversized-furniture explanation is not balance advice"
    assert found[0].principle == "visual_weight_balance"
    assert found[0].intruder == "furniture_footprint"
    assert "walking paths" in found[0].sentence


def test_the_word_even_is_not_evidence_of_balance(connectives):
    """What made run 44 return zero.

    "even though its footprint never changed" carried the section's own
    vocabulary, so the check exited before it ever looked for an intruder.
    """

    assert "even" not in dict(
        (p.name, p.vocabulary) for p in __import__(
            "vidfactory.principles", fromlist=["PRINCIPLES"]
        ).PRINCIPLES
    )["visual_weight_balance"]


def test_balance_keeps_a_mechanism_of_its_own():
    """Dropping the idea is not the fix; explaining it correctly is."""

    assert mechanism_fits("Balance visual weight across the room", "visual_balance")
    assert not mechanism_fits(
        "Balance visual weight across the room", "furniture_footprint_scale"
    )


# ----------------------------------------------------------------------
# 2. Start from the focal point and work outward
# ----------------------------------------------------------------------
FOCAL = (
    "Start from the focal point and work outward. Layouts that begin with "
    "where the sofa will fit produce rooms that function but never feel "
    "resolved. Identify the focal point, place the largest seat facing it, "
    "then add the secondary seating, then the tables, then the lighting. One "
    "piece the eye can settle on beats a wall of small ones it has to count, "
    "which is why a single generous object makes a room feel more spacious "
    "rather than busier."
)


def test_focal_point_advice_may_not_be_explained_by_statement_piece_scale(connectives):
    heading = "Start from the focal point and work outward"
    assert primary_principle(heading) is not None, (
        "a layout heading names nothing physical, so it needs a principle of "
        "its own or nothing can be compared against it"
    )
    found = find_principle_contamination(heading, FOCAL, None, connectives=connectives)
    assert found
    assert found[0].principle == "focal_point_layout"
    assert found[0].intruder == "statement_piece_scale"


def test_the_repair_refuses_the_statement_piece_family_outright():
    heading = "Start from the focal point and work outward"
    assert not mechanism_fits(heading, "statement_piece_scale")
    assert mechanism_fits(heading, "furniture_placement")


# ----------------------------------------------------------------------
# 3. Do not block the window
# ----------------------------------------------------------------------
WINDOW = (
    "This one is simple: do not block the window. Daylight is the most "
    "valuable thing in a room, and a tall piece of furniture in front of the "
    "glass costs you light in every direction. Keep anything above "
    "windowsill height away from the window wall. If a piece must go there, "
    "choose something low or open in construction. Light reaching the walls "
    "and corners shows your eye exactly where the room ends, and a room whose "
    "boundaries are visible reads as larger than one that fades into shadow a "
    "few feet in."
)

CURTAINS_ON_THE_WINDOW = (
    "This one is simple: do not block the window. Keep anything above "
    "windowsill height away from the window wall. Hanging the fabric high and "
    "wide leaves the glass itself uncovered, so more daylight reaches the "
    "room and the wall reads taller than it measures."
)


def test_window_advice_may_not_be_explained_by_perimeter_lighting(connectives):
    heading = "Do not block the window"
    found = find_principle_contamination(heading, WINDOW, None, connectives=connectives)
    assert found
    assert found[0].principle == "window_daylight"
    assert found[0].intruder == "light_reflection"


def test_the_window_is_not_the_curtain(connectives):
    """A bare window used to read as window dressing.

    That is why "hanging the fabric high and wide" could be appended to advice
    about where a tall piece of furniture goes: the section and the sentence
    were both filed under curtains.

    Note what this case proves, because it is the reason the family filter
    exists at all. *Neither* post-hoc check sees this sentence: it names the
    glass and the daylight, which are the window section's own words, so the
    concept check reads it as a normal comparison and the principle check
    exits before it looks for an intruder. Only refusing the family it came
    from keeps it out, and that is a fact about the repair rather than an
    inference from its wording.
    """

    heading = "Do not block the window"
    assert not find_contamination(heading, CURTAINS_ON_THE_WINDOW)
    assert not find_principle_contamination(
        heading, CURTAINS_ON_THE_WINDOW, None, connectives=connectives
    )
    assert not mechanism_fits(heading, "window_geometry")
    assert not mechanism_fits(heading, "window_dressing")
    # And a curtain section may still be explained through curtains.
    assert mechanism_fits("Hang curtains close to the ceiling", "window_geometry")


# ----------------------------------------------------------------------
# 4. Aim for at least three light sources per room
# ----------------------------------------------------------------------
THREE_LIGHTS = (
    "Aim for at least three light sources per room. Ceiling for general "
    "light, a lamp near seating for reading, and something low or "
    "wall-mounted for atmosphere. In the evening, use only the lower two. "
    "One ceiling light produces a flat, shadowless, institutional wash. "
    "Multiple pools of light create the depth that makes a room feel "
    "considered. If you choose the wall finish, light on the walls makes the "
    "boundaries of the room visible, which makes the whole space feel bigger "
    "than a single pool of light in the centre."
)


def test_a_lighting_section_is_not_conditioned_on_a_wall_finish():
    heading = "Aim for at least three light sources per room"
    found = find_false_conditioning(heading, THREE_LIGHTS)
    assert found, "the section never offers a wall finish as an option"
    assert found[0].used == "wall_finish"
    assert found[0].kind == "false_condition"


def test_wall_mounted_is_a_lamp_not_a_wall():
    """The trigger that started it, fixed at source.

    "Something low or wall-mounted for atmosphere" is one of three lighting
    options. Reading ``wall`` out of ``wall-mounted`` made the wall finish
    look like a fourth, which is what the conditioner then offered the reader.
    """

    offered = entities_in(
        "Ceiling for general light, a lamp near seating for reading, and "
        "something low or wall-mounted for atmosphere."
    )
    assert "wall_finish" not in offered
    assert "lighting" in offered


def test_a_genuine_optional_example_still_leaks(connectives):
    """The run 25 case the conditioner exists for is untouched."""

    heading = "Leave the corners of the room resolved"
    text = (
        "Leave the corners of the room resolved. A tall plant, a floor lamp, "
        "a leaning mirror or a single chair with a small table. A reflection "
        "adds depth, so the room reads larger than it measures."
    )
    leaks = find_optional_example_leakage(heading, text, None, connectives=connectives)
    assert leaks and leaks[0].used == "mirror"
    assert leaks[0].kind == "leakage"


# ----------------------------------------------------------------------
# End to end: the generator cannot write any of the four any more.
# ----------------------------------------------------------------------
FORBIDDEN = {
    "Balance visual weight across the room": ("walking path", "footprint", "eats"),
    "Start from the focal point and work outward": ("one substantial piece", "small ones"),
    "Do not block the window": ("the fabric", "perimeter", "pool of light"),
    "Aim for at least three light sources per room": ("if you choose the",),
}


def test_the_generator_no_longer_writes_any_of_the_four():
    language = resolve_language("en")
    seen: set[str] = set()
    for _ in range(6):
        engine = TopicEngine(history=[], similarity_threshold=0.62, language=language)
        topic = engine.from_user_input(TITLE)
        script = generate_script(
            topic,
            duration_minutes=10.0,
            engine="template",
            words_per_minute=182.09,
            llm_settings={},
            language=language,
        )
        assert not script.causal.contamination
        assert not script.causal.principle_contamination
        assert not script.causal.leakage
        for section in script.sections:
            for heading, banned in FORBIDDEN.items():
                if heading.lower() not in section.heading.lower():
                    continue
                seen.add(heading)
                lowered = section.text.lower()
                for phrase in banned:
                    assert phrase not in lowered, (
                        f"{heading!r} still explains itself with {phrase!r}: "
                        f"{section.text}"
                    )
    assert seen, "none of the four sections was generated; the test proved nothing"
