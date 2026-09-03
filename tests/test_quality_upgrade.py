"""Regression tests for the quality upgrade.

Each test here corresponds to a specific defect found in the first production
video, so a future change that reintroduces one of them fails loudly.
"""

# These tests are about the ENGLISH pipeline. The channel's default language
# is Spanish now, so every generation here says which language it means
# rather than relying on the default staying what it was when they were
# written. The Spanish equivalents live in test_spanish_and_subtitles.py.

from __future__ import annotations

import random
from pathlib import Path

import pytest

from vidfactory.editor import ShotPlan, estimate_shot_count, plan_shots
from vidfactory.editorial_qc import build_report
from vidfactory.knowledge import tips_for
from vidfactory.queries import (
    BROAD,
    GENERIC,
    SPECIFIC,
    VARIANT,
    expand_queries,
    generic_ratio,
    order_by_specificity,
)
from vidfactory.ranking import (
    BLOCKING_SIGNALS,
    ClipRanker,
    DiversitySettings,
    RankingContext,
    diversity_report,
    diversify,
    is_blocked,
    score_aspirational,
    visual_subject,
)
from vidfactory.scene_planner import plan_scenes
from vidfactory.script_generator import generate_script
from vidfactory.stock.base import StockClip
from vidfactory.stock.pexels import PexelsProvider
from vidfactory.title_alignment import (
    detect_promise,
    filter_aligned,
    score_alignment,
)
from vidfactory.topic_engine import TopicEngine


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

class _Inner:
    def __init__(self, key: str, author: str, score: float = 90.0) -> None:
        self.key = key
        self.author = author
        self.score = score


class FakeClip:
    def __init__(self, path: Path, key: str, author: str = "someone", duration: float = 15.0):
        path.write_bytes(b"x")
        self.path = str(path)
        self.duration = duration
        self.clip = _Inner(key, author)


def make_clips(tmp_path: Path, count: int, authors: int = 8) -> list[FakeClip]:
    return [
        FakeClip(tmp_path / f"c{i}.mp4", f"pexels:{1000 + i}", f"creator{i % authors}")
        for i in range(count)
    ]


def stock(provider_id: str, **kwargs) -> StockClip:
    payload = dict(
        provider="pexels",
        provider_id=provider_id,
        download_url="https://example.invalid/a.mp4",
        width=1920,
        height=1080,
        duration=14.0,
        author="Someone",
        query="bright living room natural light",
        description="bright styled living room natural light",
    )
    payload.update(kwargs)
    return StockClip(**payload)


# ==========================================================================
# 1. No provider video ID may be used twice in one video
# ==========================================================================

def test_no_source_video_is_used_twice(tmp_path):
    scenes = [(f"s{i}", 10.0) for i in range(12)]
    needed = estimate_shot_count(scenes, 3, 6)
    plan = plan_shots(scenes, make_clips(tmp_path, needed), 3, 6, rng=random.Random(1))

    keys = [shot.clip_key for shot in plan.shots]
    assert len(keys) == len(set(keys)), "a source video was used more than once"
    assert plan.reuse_count == 0
    assert plan.unique_source_ratio == 1.0


def test_a_second_segment_of_the_same_source_is_not_a_substitute(tmp_path):
    """Taking another timestamp from an already-used clip counts as reuse."""

    scenes = [("s1", 60.0)]
    plan = plan_shots(scenes, make_clips(tmp_path, 3), 3, 6, rng=random.Random(2))
    assert plan.reuse_count > 0, "reuse must be reported, not quietly allowed"
    # and every forced repeat must at least come from a different in-point
    by_key: dict[str, list[float]] = {}
    for shot in plan.shots:
        by_key.setdefault(shot.clip_key, []).append(shot.start)
    for starts in by_key.values():
        if len(starts) > 1:
            assert len(set(round(s, 1) for s in starts)) > 1


def test_reuse_can_be_disabled_outright(tmp_path):
    with pytest.raises(ValueError):
        plan_shots(
            [("s1", 60.0)], make_clips(tmp_path, 2), 3, 6,
            rng=random.Random(3), allow_reuse=False,
        )


# ==========================================================================
# 2. The original bug: the clip sequence must never replay in order
# ==========================================================================

def test_the_clip_sequence_never_replays_in_the_same_order(tmp_path):
    """The v1 planner cycled `order[cursor % len(order)]`, replaying the head."""

    scenes = [(f"s{i}", 12.0) for i in range(10)]
    clips = make_clips(tmp_path, 6)          # deliberately far too few
    plan = plan_shots(scenes, clips, 3, 6, rng=random.Random(4))

    keys = [shot.clip_key for shot in plan.shots]
    unique = len(set(keys))
    # Any window the size of the clip pool must not repeat the first window.
    first_window = keys[:unique]
    for offset in range(unique, len(keys) - unique + 1):
        assert keys[offset : offset + unique] != first_window, (
            "the clip order repeats verbatim later in the video"
        )


def test_shot_count_estimate_matches_what_the_planner_produces(tmp_path):
    """Under-counting here is what starved the first video of footage."""

    for scene_count, seconds in ((6, 9.0), (12, 11.0), (20, 7.5)):
        scenes = [(f"s{i}", seconds) for i in range(scene_count)]
        predicted = estimate_shot_count(scenes, 3, 6)
        plan = plan_shots(scenes, make_clips(tmp_path, predicted + 5), 3, 6,
                          rng=random.Random(5))
        assert len(plan.shots) == predicted


# ==========================================================================
# 3. Shot pacing and creator diversity
# ==========================================================================

def test_shots_are_three_to_six_seconds_with_an_irregular_rhythm(tmp_path):
    scenes = [(f"s{i}", 20.0) for i in range(6)]
    plan = plan_shots(scenes, make_clips(tmp_path, 40), 3, 6, rng=random.Random(6))
    durations = [s.duration for s in plan.shots]
    assert max(durations) <= 6.1
    assert min(durations) >= 2.0
    # A constant cadence is what makes long videos feel robotic.
    assert len({round(d, 1) for d in durations}) > 4


def test_no_more_than_two_consecutive_clips_from_one_creator(tmp_path):
    scenes = [(f"s{i}", 10.0) for i in range(10)]
    # Only three creators, so the rule has to actively work.
    clips = make_clips(tmp_path, 40, authors=3)
    plan = plan_shots(scenes, clips, 3, 6, rng=random.Random(7))

    authors = {c.clip.key: c.clip.author for c in clips}
    run = 1
    worst = 1
    for previous, current in zip(plan.shots, plan.shots[1:]):
        if authors[previous.clip_key] == authors[current.clip_key]:
            run += 1
            worst = max(worst, run)
        else:
            run = 1
    assert worst <= 2, f"{worst} consecutive clips from one creator"


def test_scene_affinity_keeps_an_ideas_shots_together(tmp_path):
    clips = make_clips(tmp_path, 20)
    affinity = {
        "s0": [c.clip.key for c in clips[:5]],
        "s1": [c.clip.key for c in clips[5:10]],
    }
    plan = plan_shots(
        [("s0", 15.0), ("s1", 15.0)], clips, 3, 6,
        rng=random.Random(8), scene_affinity=affinity,
    )
    for shot in plan.shots:
        assert shot.clip_key in affinity[shot.scene_id], (
            "a scene used footage found for a different idea"
        )


# ==========================================================================
# 4. Query specificity and fallback ordering
# ==========================================================================

def test_specific_queries_come_before_generic_ones():
    ladder = expand_queries(
        ["floor to ceiling curtains living room", "tall curtains modern interior"],
        narration="Hang your curtains close to the ceiling.",
        category_queries=["modern living room interior"],
    )
    ordered = order_by_specificity(ladder)
    kinds = [q.specificity for q in ordered]
    assert kinds.index(SPECIFIC) < kinds.index(GENERIC)
    assert ordered[-1].is_generic
    assert not ordered[0].is_generic


def test_at_least_five_specific_variants_per_concept():
    ladder = expand_queries(
        ["floor to ceiling curtains living room"],
        narration="Hang your curtains close to the ceiling to make the room feel taller.",
        category_queries=["modern living room interior"],
    )
    specific = [q for q in ladder if q.specificity in (SPECIFIC, VARIANT)]
    assert len(specific) >= 5


def test_queries_include_both_wide_and_detail_framings():
    ladder = expand_queries(
        ["floor to ceiling curtains living room", "tall curtains modern interior"],
        category_queries=["modern living room interior"],
    )
    shot_types = {q.shot_type for q in ladder if q.shot_type}
    assert {"wide", "detail"} <= shot_types


def test_every_scene_gets_enough_specific_queries():
    topic = TopicEngine(language="en").from_user_input(
        "5 Small Living Room Tricks That Make Your Space Look Bigger"
    )
    scenes = plan_scenes(generate_script(topic, 2.0, language="en"))
    for scene in scenes:
        assert len(scene.specific_queries) >= 5, scene.scene_id
    assert generic_ratio([q for s in scenes for q in s.visual_queries]) < 0.4


def test_query_diversity_across_a_video():
    topic = TopicEngine(language="en").from_user_input("Cozy Bedroom Ideas For A Warmer Home")
    scenes = plan_scenes(generate_script(topic, 5.0, language="en"))
    primaries = [s.visual_queries[0].text for s in scenes]
    assert len(set(primaries)) / len(primaries) > 0.4


# ==========================================================================
# 5. Aspirational quality filter
# ==========================================================================

@pytest.mark.parametrize(
    "caption",
    [
        "a woman cleaning the living room",
        "sofa wrapped in plastic during a move",
        "empty room under construction with tools",
        "demolition of an old kitchen",
    ],
)
def test_unaspirational_footage_is_rejected(caption):
    clip = stock("1", description=caption, query="living room")
    assert is_blocked(clip)
    assert score_aspirational(clip)[0] == 0.0
    assert not ClipRanker().is_eligible(clip, RankingContext(query="living room"))


@pytest.mark.parametrize(
    "caption",
    [
        "modern bright living room with large windows and natural light",
        "cozy scandinavian bedroom with linen bedding sunlight",
        "elegant styled interior design apartment",
    ],
)
def test_aspirational_footage_scores_well(caption):
    assert score_aspirational(stock("1", description=caption))[0] >= 0.7


def test_soft_negatives_are_down_ranked_not_rejected():
    clip = stock("1", description="man watching television with a remote control", query="")
    assert not is_blocked(clip)
    score, reasons = score_aspirational(clip)
    assert 0.0 < score < 0.5
    assert any(r.startswith("-") for r in reasons)


def test_missing_caption_is_neutral():
    score, _ = score_aspirational(stock("1", description="", query="", tags=[]))
    assert 0.4 < score < 0.7


def test_aspirational_beats_a_technically_better_but_wrong_clip():
    good = stock("1", description="bright styled living room natural light", width=1920, height=1080)
    bad = stock("2", description="a woman vacuuming a messy living room", width=3840, height=2160)
    ranked = ClipRanker().rank([bad, good], RankingContext(query="living room"))
    assert [c.provider_id for c in ranked] == ["1"]


def test_the_enforcement_can_be_switched_off():
    clip = stock("1", description="a woman cleaning the living room")
    context = RankingContext(query="living room", enforce_aspirational=False)
    assert ClipRanker().is_eligible(clip, context)


def test_pexels_caption_is_recovered_from_the_page_url():
    assert PexelsProvider.describe(
        "https://www.pexels.com/video/a-woman-cleaning-the-living-room-1234567/"
    ) == "a woman cleaning the living room"
    assert PexelsProvider.describe("") == ""


# ==========================================================================
# 6. Per-video diversity
# ==========================================================================

def test_one_creator_cannot_dominate_the_selection():
    # 20 clips from one prolific creator ranked above 20 from distinct others.
    subjects = ["sofa", "curtain", "rug", "lamp", "mirror", "plant", "shelf", "bed"]
    clips = [
        stock(str(i), author="Prolific", score=100 - i,
              description=f"{subjects[i % len(subjects)]} in a styled interior")
        for i in range(20)
    ]
    clips += [
        stock(str(100 + i), author=f"Other{i}", score=70 - i,
              description=f"{subjects[i % len(subjects)]} in a bright room")
        for i in range(20)
    ]
    chosen = diversify(clips, 20, DiversitySettings(max_creator_share=0.2))
    prolific = sum(1 for c in chosen if c.author == "Prolific")
    assert len(chosen) == 20
    assert prolific <= max(2, int(20 * 0.2)) + 1, f"{prolific} clips from one creator"


def test_one_query_cannot_dominate_the_selection():
    subjects = ["sofa", "curtain", "rug", "lamp", "mirror", "plant", "shelf", "bed"]
    clips = [
        stock(str(i), query="modern living room", author=f"a{i}", score=100 - i,
              description=f"{subjects[i % len(subjects)]} interior")
        for i in range(20)
    ]
    clips += [
        stock(str(100 + i), query=f"query{i}", author=f"b{i}", score=70 - i,
              description=f"{subjects[i % len(subjects)]} interior")
        for i in range(20)
    ]
    chosen = diversify(clips, 20, DiversitySettings(max_query_share=0.2))
    dominant = sum(1 for c in chosen if c.query == "modern living room")
    assert len(chosen) == 20
    assert dominant <= max(2, int(20 * 0.2)) + 1, f"{dominant} clips from one query"


def test_diversity_caps_never_starve_the_video():
    clips = [stock(str(i), author="OnlyOne", query="one query") for i in range(12)]
    assert len(diversify(clips, 10)) == 10


def test_diversity_report_metrics():
    clips = [stock(str(i), author=f"creator{i % 4}", query=f"q{i % 3}") for i in range(12)]
    report = diversity_report(clips)
    assert report["distinct_creators"] == 4
    assert report["distinct_queries"] == 3
    assert 0 < report["creator_diversity"] <= 1


def test_visual_subject_detection():
    assert visual_subject(stock("1", description="tall curtains by a window", query="")) == "curtain"
    assert visual_subject(stock("1", description="abstract motion graphic", query="")) == "interior"


# ==========================================================================
# 7. Title / idea alignment
# ==========================================================================

def test_the_promise_is_detected_from_the_title():
    assert detect_promise("25 Ideas That Make Any Space Look Bigger").key == "bigger"
    assert detect_promise("20 Ways To Make Your Home Look More Expensive").key == "expensive"
    assert detect_promise("25 Smart Storage Ideas").key == "storage"
    assert detect_promise("30 Modern Living Room Ideas").key == "general"


def test_an_ergonomic_tip_does_not_belong_in_a_look_bigger_video():
    """The user's own example: coffee table height is not a space trick."""

    promise = detect_promise("5 Small Living Room Ideas That Make Your Space Look Bigger")
    tip = next(
        t for t in tips_for(None) if "coffee table height" in t["title"].lower()
    )
    result = score_alignment(tip, promise)
    assert not result.aligned, result.explain()


def test_a_space_trick_does_belong():
    promise = detect_promise("5 Small Living Room Ideas That Make Your Space Look Bigger")
    tip = next(t for t in tips_for(None) if "visible legs" in t["title"].lower())
    assert score_alignment(tip, promise).aligned


def test_generated_scripts_only_contain_aligned_ideas():
    topic = TopicEngine(language="en").from_user_input(
        "25 Small Living Room Ideas That Make Any Space Look Bigger"
    )
    script = generate_script(topic, 20.0, language="en")
    assert script.promise_key == "bigger"
    assert script.title_idea_alignment >= 0.9
    assert script.rejected_ideas, "nothing was rejected, so nothing was validated"
    headings = " ".join(s.heading.lower() for s in script.items())
    assert "coffee table height" not in headings


def test_a_general_title_accepts_every_idea():
    topic = TopicEngine(language="en").from_user_input("Modern Living Room Ideas")
    script = generate_script(topic, 10.0, language="en")
    assert script.promise_key == "general"
    assert script.title_idea_alignment == 1.0


def test_filtering_never_leaves_a_video_unbuildable():
    promise = detect_promise("20 Ways To Make Your Home Look More Expensive")
    kept, _ = filter_aligned(tips_for("bathrooms"), promise, minimum=5)
    assert len(kept) >= 5


# ==========================================================================
# 8. Editorial QC
# ==========================================================================

def _report(tmp_path, clip_count: int, scene_seconds: float = 10.0, scenes: int = 8):
    scene_list = [(f"s{i}", scene_seconds) for i in range(scenes)]
    plan = plan_shots(scene_list, make_clips(tmp_path, clip_count), 3, 6,
                      rng=random.Random(9))

    class FakeScene:
        def __init__(self, sid, idx):
            self.scene_id = sid
            self.section_index = idx

    class FakeScript:
        title_idea_alignment = 1.0
        promise_key = "bigger"
        rejected_ideas: list = []

    fake_scenes = [FakeScene(f"s{i}", i) for i in range(scenes)]
    clips = [type("C", (), {"clip": _Inner(f"pexels:{i}", f"creator{i%6}", 80.0)})()
             for i in range(clip_count)]
    return build_report(
        shot_plan=plan,
        clips=clips,
        scenes=fake_scenes,
        script=FakeScript(),
        search_stats={"specific_queries_run": 40, "generic_queries_run": 2},
        diversity={"creator_diversity": 0.8, "query_diversity": 0.7},
    )


def test_editorial_qc_passes_a_clean_edit(tmp_path):
    needed = estimate_shot_count([(f"s{i}", 10.0) for i in range(8)], 3, 6)
    report = _report(tmp_path, needed)
    assert report.passed, [c.detail for c in report.failures]
    assert report.metrics["source_video_reuse_count"] == 0
    assert report.metrics["unique_source_ratio"] == 1.0


def test_editorial_qc_fails_a_repetitive_edit(tmp_path):
    report = _report(tmp_path, 4)
    assert not report.passed
    names = {c.name for c in report.failures}
    assert "no_source_video_reuse" in names
    assert "unique_source_ratio" in names


def test_editorial_report_contains_every_requested_metric(tmp_path):
    report = _report(tmp_path, estimate_shot_count([(f"s{i}", 10.0) for i in range(8)], 3, 6))
    payload = report.to_dict()
    for key in (
        "source_video_reuse_count",
        "unique_source_ratio",
        "generic_query_percentage",
        "average_clip_score",
        "creator_diversity",
        "query_diversity",
        "title_idea_alignment",
        "shot_count",
        "visual_coverage_per_section",
    ):
        assert key in payload, key


def test_editorial_report_flags_excessive_generic_queries(tmp_path):
    scenes = [(f"s{i}", 10.0) for i in range(4)]
    plan = plan_shots(scenes, make_clips(tmp_path, 40), 3, 6, rng=random.Random(10))

    class FakeScript:
        title_idea_alignment = 1.0
        promise_key = "bigger"
        rejected_ideas: list = []

    report = build_report(
        shot_plan=plan,
        clips=[],
        scenes=[],
        script=FakeScript(),
        search_stats={"specific_queries_run": 2, "generic_queries_run": 20},
        diversity={"creator_diversity": 0.9},
    )
    generic = next(c for c in report.checks if c.name == "generic_query_usage")
    assert not generic.passed
    assert generic.severity == "warning"


def test_editorial_report_saves_json(tmp_path):
    report = _report(tmp_path, estimate_shot_count([(f"s{i}", 10.0) for i in range(8)], 3, 6))
    path = report.save(tmp_path / "editorial_quality_report.json")
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["passed"] is True


# ==========================================================================
# 9. Writing quality
# ==========================================================================

BANNED_PHRASES = (
    "The thinking behind this is simple",
    "Here is how to apply it",
    "There is a real principle underneath this",
    "Do this one thing",
    "The reason is straightforward",
    "In practice, here is how to do it",
)


def test_the_formulaic_connectives_are_gone():
    topic = TopicEngine(language="en").from_user_input(
        "25 Small Living Room Ideas That Make Any Space Look Bigger"
    )
    text = generate_script(topic, 20.0, language="en").text
    for phrase in BANNED_PHRASES:
        assert phrase not in text, phrase


def test_items_do_not_all_follow_one_sentence_shape():
    topic = TopicEngine(language="en").from_user_input("Cozy Bedroom Ideas For A Warmer Home")
    items = generate_script(topic, 15.0, language="en").items()
    openings = {" ".join(s.text.split()[:3]) for s in items}
    assert len(openings) > len(items) * 0.5


def test_the_hook_creates_curiosity_without_channel_boilerplate():
    topic = TopicEngine(language="en").from_user_input(
        "5 Small Living Room Tricks That Make Your Space Look Bigger"
    )
    intro = generate_script(topic, 2.0, language="en").sections[0].text.lower()
    for boilerplate in ("welcome to", "subscribe", "hit the like", "my channel"):
        assert boilerplate not in intro
    assert len(intro.split()) >= 20


def test_the_hook_is_promise_aware():
    bigger = generate_script(
        TopicEngine(language="en").from_user_input("25 Ideas That Make Any Space Look Bigger"), 5.0, language="en").sections[0].text
    expensive = generate_script(
        TopicEngine(language="en").from_user_input("25 Ways To Make Your Home Look More Expensive"), 5.0, language="en").sections[0].text
    assert bigger != expensive
