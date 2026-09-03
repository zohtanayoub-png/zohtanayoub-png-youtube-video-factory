"""Run 16's editorial failures, each pinned as a test.

Run 16 was technically clean - zero source reuse, provenance passed, causal
alignment 0.95 - and still shipped paragraphs that argued against their own
headings, an idea that had nothing to do with the title, and footage that did
not show the narration. Every test here is one of those, written from the
actual text or number the run produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from vidfactory.causal_alignment import (
    PASS_THRESHOLD,
    repair_text,
    score_paragraph,
    validate_sections,
)
from vidfactory.contradiction import (
    find_contradictions,
    read_direction,
    split_recommendation,
)
from vidfactory.database import Database
from vidfactory.knowledge import KNOWLEDGE
from vidfactory.scene_planner import build_shot_intents, shot_chunks
from vidfactory.title_alignment import (
    detect_promise,
    mechanism_by_name,
    rank_mechanisms,
    score_alignment,
)

BIGGER = detect_promise("Small Living Room Tricks That Make Your Space Look Bigger", "")

TIPS = {tip["title"]: tip for tips in KNOWLEDGE.values() for tip in tips}


@dataclass
class FakeSection:
    index: int
    heading: str
    text: str
    kind: str = "item"
    tip: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. The contradiction itself
# ---------------------------------------------------------------------------

#: Verbatim from run 16's script.
RUN16_STATEMENT_PIECE = (
    "Scale is expensive to fake. One oversized mirror, lamp or artwork will "
    "always look more considered than a wall of small purchases. Oversized "
    "pieces eat visible floor area and narrow the walking paths, so a small "
    "room feels cramped even though its footprint never changed."
)

RUN16_RUG = (
    "A rug defines the seating zone. A piece that is too big for the room "
    "steals the floor around it, so what is left over feels cramped even "
    "though nothing else changed."
)


def test_run16_statement_piece_paragraph_is_detected_as_contradictory():
    found = find_contradictions(
        "Buy one bigger thing instead of three medium things", RUN16_STATEMENT_PIECE
    )
    assert found, "the run 16 paragraph argues against its own heading"
    assert found[0].axis == "scale"
    assert found[0].recommends == "more"
    assert "cramped" in found[0].harm


def test_run16_rug_paragraph_is_detected_as_contradictory():
    found = find_contradictions(
        "Buy a rug that is genuinely too big rather than slightly too small",
        RUN16_RUG,
    )
    assert found
    assert found[0].axis == "scale"


def test_the_causal_score_alone_never_saw_the_contradiction():
    """Both paragraphs scored perfectly, which is why a new check was needed."""

    assert score_paragraph(RUN16_STATEMENT_PIECE, BIGGER).score >= PASS_THRESHOLD
    assert score_paragraph(RUN16_RUG, BIGGER).score >= PASS_THRESHOLD


def test_describing_the_mistake_is_not_a_contradiction():
    """Contrasting the advice with the error is how decorating writing works."""

    assert not find_contradictions(
        "Choose a rug that is generously sized, not undersized",
        "An undersized rug leaves the furniture floating with no anchor, so the "
        "seating group reads as scattered and the room feels smaller than it is.",
    )


def test_a_heading_with_no_stance_cannot_contradict():
    assert not find_contradictions(
        "Balance visual weight across the room",
        "Oversized furniture eats visible floor area and narrows the walking "
        "paths, so a small room feels cramped.",
    )


@pytest.mark.parametrize(
    "heading, recommended, avoided",
    [
        ("Buy one bigger thing instead of three medium things",
         "bigger", "three medium"),
        ("Choose a rug that is generously sized, not undersized",
         "generously sized", "undersized"),
        ("Add one oversized plant instead of five small ones",
         "oversized plant", "five small ones"),
    ],
)
def test_the_recommendation_is_separated_from_the_mistake(heading, recommended, avoided):
    action, avoid = split_recommendation(heading)
    assert recommended in action
    assert avoided in avoid


def test_the_direction_names_all_four_parts():
    direction = read_direction(
        "Buy one bigger thing instead of three medium things",
        mechanism="statement_piece_scale",
        outcome="more spacious",
    )
    assert direction.recommended_action
    assert direction.thing_to_avoid
    assert direction.mechanism == "statement_piece_scale"
    assert direction.desired_outcome == "more spacious"
    assert direction.stance["scale"] == 1


# ---------------------------------------------------------------------------
# 2. The repair must not re-introduce it
# ---------------------------------------------------------------------------

def test_repair_refuses_an_explanation_that_reverses_the_advice():
    heading = "Buy one bigger thing instead of three medium things"
    tip = TIPS["Buy one bigger thing instead of three medium things"]
    repaired = repair_text(tip["why"], BIGGER, tip, heading=heading)
    assert repaired is not None
    assert not find_contradictions(heading, repaired)
    assert "eat visible floor area" not in repaired


def test_a_contradicting_paragraph_is_rewritten_not_shipped():
    section = FakeSection(
        index=1,
        heading="Buy one bigger thing instead of three medium things",
        text=RUN16_STATEMENT_PIECE,
        tip=TIPS["Buy one bigger thing instead of three medium things"],
    )
    report = validate_sections([section], BIGGER, rewrite=True)
    assert report.contradiction.count == 0
    assert report.contradiction.rewrites == 1
    assert "eat visible floor area" not in section.text
    assert score_paragraph(section.text, BIGGER).score >= PASS_THRESHOLD


def test_the_report_counts_surviving_contradictions():
    """A heading whose only mechanism argues the other way cannot be repaired."""

    section = FakeSection(
        index=1,
        heading="Choose a brighter wall color",
        text="A dark wall absorbs the light and the room feels cramped.",
    )
    report = validate_sections([section], BIGGER, rewrite=False)
    payload = report.to_dict()
    assert "contradiction_count" in payload
    assert payload["contradiction_count"] == report.contradiction.count


# ---------------------------------------------------------------------------
# 3. A statement piece is not an oversized sofa
# ---------------------------------------------------------------------------

def test_the_two_scale_mechanisms_are_separate():
    statement = mechanism_by_name(BIGGER, "statement_piece_scale")
    footprint = mechanism_by_name(BIGGER, "furniture_footprint_scale")
    assert statement is not None and footprint is not None
    assert not set(statement.explanations) & set(footprint.explanations)
    assert not set(statement.words) & set(footprint.words)


def test_statement_piece_advice_uses_the_fragmentation_explanation():
    tip = TIPS["Buy one bigger thing instead of three medium things"]
    names = [m.name for m in rank_mechanisms(BIGGER, f"{tip['title']} {tip['why']}")]
    assert names[0] == "statement_piece_scale"
    assert "furniture_footprint_scale" not in names


def test_oversized_furniture_advice_still_uses_the_footprint_explanation():
    text = "An oversized sofa with a deep seat depth swallows a small living room."
    names = [m.name for m in rank_mechanisms(BIGGER, text)]
    assert "furniture_footprint_scale" in names
    assert "statement_piece_scale" not in names


# ---------------------------------------------------------------------------
# 4. The rug
# ---------------------------------------------------------------------------

def test_the_rug_idea_no_longer_recommends_a_rug_that_is_too_big():
    titles = [t for t in TIPS if "rug" in t.lower()]
    assert "Buy a rug that is genuinely too big rather than slightly too small" not in titles
    assert "Choose a rug that is generously sized, not undersized" in TIPS


def test_the_rug_idea_keeps_it_proportional_to_the_room():
    tip = TIPS["Choose a rug that is generously sized, not undersized"]
    assert "proportional to the room" in tip["how"]
    assert "front legs" in tip["how"]


def test_the_rug_mechanism_blames_the_small_rug_not_the_large_one():
    rug = mechanism_by_name(BIGGER, "rug_scale")
    assert rug is not None
    for explanation in rug.explanations:
        assert not find_contradictions(
            "Choose a rug that is generously sized, not undersized", explanation
        )


def test_rug_advice_picks_the_rug_mechanism():
    tip = TIPS["Choose a rug that is generously sized, not undersized"]
    names = [m.name for m in rank_mechanisms(BIGGER, f"{tip['title']} {tip['why']} {tip['how']}")]
    assert names[0] == "rug_scale"


# ---------------------------------------------------------------------------
# 5. Ideas that only fit the title if you squint
# ---------------------------------------------------------------------------

def test_material_mixing_is_rejected_for_a_look_bigger_title():
    result = score_alignment(TIPS["Mix at least three materials in every room"], BIGGER)
    assert not result.aligned
    assert result.score == 0.0
    assert result.denied_by


def test_a_secondary_mention_of_reflection_cannot_rescue_it():
    tip = dict(TIPS["Mix at least three materials in every room"])
    tip["why"] = tip["why"] + " A mirror makes the room look bigger and more spacious."
    assert not score_alignment(tip, BIGGER).aligned


def test_genuine_space_tricks_are_not_caught_by_the_subject_filter():
    for title in (
        "Keep one continuous flooring material",
        "Choose a rug that is generously sized, not undersized",
        "Buy one bigger thing instead of three medium things",
    ):
        assert score_alignment(TIPS[title], BIGGER).aligned, title


# ---------------------------------------------------------------------------
# 7. Shot-specific visual intent
# ---------------------------------------------------------------------------

def test_narration_is_split_into_shot_length_chunks():
    narration = (
        "An undersized rug makes the seating group feel disconnected. "
        "Choose one large enough for the front legs of every seat. "
        "That connects the seating area into one visual zone."
    )
    chunks = shot_chunks(narration)
    assert len(chunks) == 3
    assert all(2 <= len(c.split()) <= 20 for c in chunks)


def test_each_shot_gets_its_own_intent_and_query():
    from vidfactory.queries import VisualQuery

    queries = [
        VisualQuery("large living room rug sofa", 0),
        VisualQuery("sofa front legs on rug", 1),
        VisualQuery("wide living room rug", 2),
    ]
    intents = build_shot_intents(
        "item-001-00",
        "An undersized rug makes the seating group feel disconnected. "
        "Choose one large enough for the front legs of every seat. "
        "That connects the seating area into one visual zone.",
        "rug scale living room",
        queries,
    )
    assert len(intents) == 3
    assert len({i.query for i in intents}) == 3
    assert all(i.search_text for i in intents)
    assert all(i.search_text.isascii() for i in intents)


def test_shot_intents_stay_english_for_a_spanish_scene():
    from vidfactory.queries import VisualQuery

    intents = build_shot_intents(
        "item-001-00",
        "Una alfombra pequeña deja los muebles flotando en el suelo.",
        "rug scale living room",
        [VisualQuery("large living room rug sofa", 0)],
    )
    assert intents
    assert all(i.search_text.isascii() for i in intents)


# ---------------------------------------------------------------------------
# 10. Development renders must not claim production footage
# ---------------------------------------------------------------------------

def test_a_test_render_does_not_put_a_clip_on_cooldown():
    db = Database(":memory:")
    db.initialize()
    db.record_clip_use("pexels", "12345", mode=Database.TEST)
    assert not db.is_clip_on_cooldown("pexels", "12345", 45)


def test_a_production_render_does_put_a_clip_on_cooldown():
    db = Database(":memory:")
    db.initialize()
    db.record_clip_use("pexels", "12345", mode=Database.PRODUCTION)
    assert db.is_clip_on_cooldown("pexels", "12345", 45)


def test_a_test_render_does_not_clear_an_existing_production_cooldown():
    db = Database(":memory:")
    db.initialize()
    db.record_clip_use("pexels", "12345", mode=Database.PRODUCTION)
    db.record_clip_use("pexels", "12345", mode=Database.TEST)
    assert db.is_clip_on_cooldown("pexels", "12345", 45)
    stats = db.clip_mode_stats()
    assert stats["production"] == 1 and stats["test"] == 1


def test_releasing_development_history_frees_the_footage_without_deleting_it():
    db = Database(":memory:")
    db.initialize()
    db.record_clip_use("pexels", "1", mode=Database.PRODUCTION)
    db.record_clip_use("pexels", "2", mode=Database.PRODUCTION)

    preview = db.reclassify_clip_history(dry_run=True)
    assert preview == {"moved": 0, "would_move": 2}
    assert db.is_clip_on_cooldown("pexels", "1", 45)

    moved = db.reclassify_clip_history()
    assert moved["moved"] == 2
    assert not db.is_clip_on_cooldown("pexels", "1", 45)
    # The rows survive: this is a reclassification, not a delete.
    assert db.clip_mode_stats()["clips"] == 2
    assert db.clip_mode_stats()["test"] == 2


def test_releasing_can_be_limited_to_one_topic():
    db = Database(":memory:")
    db.initialize()
    db.record_clip_use("pexels", "1", topic="dev-run", mode=Database.PRODUCTION)
    db.record_clip_use("pexels", "2", topic="published", mode=Database.PRODUCTION)
    db.reclassify_clip_history(topics=["dev-run"])
    assert not db.is_clip_on_cooldown("pexels", "1", 45)
    assert db.is_clip_on_cooldown("pexels", "2", 45)


# ---------------------------------------------------------------------------
# Automatic repair of weak final shots
# ---------------------------------------------------------------------------

class _Clip:
    def __init__(self, key, match, path="/tmp/x.mp4"):
        self.key = key
        self.query = "living room"
        self.author = "a"
        self.visual = {"analyzed": True, "semantic_match": match}
        self.visual_semantic_match = match


class _Entry:
    def __init__(self, clip, path="/tmp/x.mp4", duration=9.0):
        self.clip = clip
        self.path = path
        self.duration = duration


class _Shot:
    def __init__(self, scene_id, clip_key, duration=4.0):
        self.scene_id = scene_id
        self.clip_key = clip_key
        self.duration = duration
        self.start = 0.0
        self.source = None


def _pipeline_stub(monkeypatch, tmp_path, replacement_scores):
    """A Pipeline with just enough wired up to exercise the repair pass."""

    from vidfactory import pipeline as pipeline_module
    from vidfactory.config import load_config

    config = load_config()
    pipe = pipeline_module.VideoPipeline.__new__(pipeline_module.VideoPipeline)
    pipe.config = config
    pipe.workdir = tmp_path
    pipe.database = Database(":memory:")
    pipe.database.initialize()

    class _Analyzer:
        def analyze_clip(self, clip, **kwargs):
            class _A:
                semantic_match = clip.visual["semantic_match"]

                def to_dict(self):
                    return dict(clip.visual)

            return _A()

    class _Provider:
        name = "stub"
        supports_pagination = True

        def search(self, text, per_page=30, page=1):
            return [
                _Clip(f"stub:{text}:{page}:{i}", score)
                for i, score in enumerate(replacement_scores)
            ]

    monkeypatch.setattr(pipeline_module, "build_providers", lambda sources: [_Provider()])
    monkeypatch.setattr(pipeline_module, "metadata_visual_flags", lambda *a, **k: {})
    monkeypatch.setattr(pipe, "_visual_analyzer", lambda: _Analyzer())
    monkeypatch.setattr(pipe, "_clip_history", lambda: {})

    class _Ranker:
        def __init__(self, **kwargs):
            pass

        def rank(self, clips, context):
            return list(clips)

    class _Downloader:
        def __init__(self, **kwargs):
            pass

        def fetch_many(self, clips, needed=1):
            return [_Entry(c) for c in clips[:needed]]

    monkeypatch.setattr(pipeline_module, "ClipRanker", _Ranker)
    monkeypatch.setattr(pipeline_module, "ClipDownloader", _Downloader)
    return pipe


def test_weak_shots_are_repaired_rather_than_reported(monkeypatch, tmp_path):
    from vidfactory.topic_engine import Topic

    pipe = _pipeline_stub(monkeypatch, tmp_path, replacement_scores=[0.72])
    weak, strong = _Clip("p:1", 0.20), _Clip("p:2", 0.80)
    clips = [_Entry(weak), _Entry(strong)]
    shots = [_Shot("item-001-00", "p:1"), _Shot("item-001-01", "p:2")]

    updated, stats = pipe._repair_weak_shots(
        shots, clips, [], {},
        Topic(title="Small Living Room Tricks", category="small spaces"),
    )
    assert stats["weak_shots_before_repair"] == 1
    assert stats["weak_shots_after_repair"] == 0
    assert stats["repaired_shot_count"] == 1
    assert stats["repair_rounds_used"] == 1
    # The good shot was left completely alone.
    assert shots[1].clip_key == "p:2"
    assert shots[0].clip_key != "p:1"


def test_a_replacement_must_actually_score_better(monkeypatch, tmp_path):
    from vidfactory.topic_engine import Topic

    # Every alternative is worse than the clip already in place.
    pipe = _pipeline_stub(monkeypatch, tmp_path, replacement_scores=[0.10])
    weak = _Clip("p:1", 0.30)
    shots = [_Shot("item-001-00", "p:1")]

    _, stats = pipe._repair_weak_shots(
        shots, [_Entry(weak)], [], {},
        Topic(title="Small Living Room Tricks", category="small spaces"),
    )
    assert stats["repaired_shot_count"] == 0
    assert stats["weak_shots_after_repair"] == 1
    assert shots[0].clip_key == "p:1"


def test_repair_gives_up_after_three_rounds(monkeypatch, tmp_path):
    from vidfactory.topic_engine import Topic

    # Better than the original, but still under the relevance threshold.
    pipe = _pipeline_stub(monkeypatch, tmp_path, replacement_scores=[0.31])
    shots = [_Shot("item-001-00", "p:1")]

    _, stats = pipe._repair_weak_shots(
        shots, [_Entry(_Clip("p:1", 0.10))], [], {},
        Topic(title="Small Living Room Tricks", category="small spaces"),
    )
    assert stats["repair_rounds_used"] == 3
    assert stats["weak_shots_after_repair"] == 1


def test_repair_never_reuses_a_source_another_shot_holds(monkeypatch, tmp_path):
    from vidfactory.topic_engine import Topic

    pipe = _pipeline_stub(monkeypatch, tmp_path, replacement_scores=[0.9])
    weak, strong = _Clip("p:1", 0.20), _Clip("p:2", 0.80)
    shots = [_Shot("item-001-00", "p:1"), _Shot("item-001-01", "p:2")]

    updated, _ = pipe._repair_weak_shots(
        shots, [_Entry(weak), _Entry(strong)], [], {},
        Topic(title="Small Living Room Tricks", category="small spaces"),
    )
    keys = [s.clip_key for s in shots]
    assert len(keys) == len(set(keys)), "a repair introduced a duplicate source"


def test_every_mechanism_explanation_names_its_own_mechanism():
    """Otherwise the sentence that states the mechanism cannot score as doing so.

    Repair appends a mechanism's own explanation, which should take a
    paragraph to 1.00 - mechanism, connective and outcome together. Where the
    explanation uses vocabulary the mechanism does not claim, the scorer sees
    only a connective and an outcome, the paragraph sticks at 0.85, and a
    short video can never reach the average it is graded on.
    """

    from vidfactory.title_alignment import PROMISES, PROMISES_ES, mechanisms_for

    unrecognised = [
        (promise.key, promise.language, mechanism.name, text[:60])
        for promise in list(PROMISES) + list(PROMISES_ES)
        for mechanism in promise.mechanisms
        for text in mechanism.explanations
        if mechanism.name
        not in [m.name for m in mechanisms_for(promise, text.lower())]
    ]
    assert not unrecognised, (
        "these explanations state a mechanism the scorer cannot see: "
        f"{unrecognised[:3]}"
    )


def test_a_repaired_paragraph_states_its_mechanism():
    tip = TIPS["Choose a rug that is generously sized, not undersized"]
    repaired = repair_text(
        tip["why"], BIGGER, tip,
        heading="Choose a rug that is generously sized, not undersized",
    )
    assert repaired is not None
    assert score_paragraph(repaired, BIGGER).score == 1.0
