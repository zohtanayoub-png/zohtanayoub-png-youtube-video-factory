"""Regression tests for the run 6 failures.

Run 6 reported ``premium_visual_ratio = 0.912``, ``empty_room_clip_count = 0``
and ``dark_clip_count = 0`` for a video that visibly contained a floor plan, a
dog on a sofa, two nearly empty rooms and a sofa wrapped in plastic. Every
number came from Pexels captions, all of which honestly described interiors.

These tests render each of those failures as real footage with FFmpeg, decode
real frames from it, and assert the pipeline now catches what a caption never
could. Nothing here is mocked pixels: the fixtures are MP4 files and the
statistics are measured from decoded rgb24.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from vidfactory.causal_alignment import (
    PASS_THRESHOLD,
    repair_text,
    score_paragraph,
    validate_sections,
)
from vidfactory.editorial_qc import build_report
from vidfactory.ffmpeg_utils import ffmpeg_available, ffmpeg_path
from vidfactory.ranking import (
    VisualRankingSettings,
    metadata_visual_flags,
    rank_with_vision,
    visual_score,
)
from vidfactory.stock.base import StockClip
from vidfactory.title_alignment import detect_promise
from vidfactory.visual_analysis import (
    PENALTY_CONFIDENCE,
    REJECT_CONFIDENCE,
    VisualAnalyzer,
    decode_frame,
    match_expectations,
    measure,
    sample_frames,
    sample_positions,
)

pytestmark = pytest.mark.skipif(
    not ffmpeg_available(), reason="FFmpeg is required to decode real frames"
)

# ---------------------------------------------------------------------------
# Fixtures - the run 6 failures, rendered as actual video
# ---------------------------------------------------------------------------

ROOM = (
    "color=c=0xE2DCD2:s=640x360,"
    "drawbox=x=60:y=190:w=260:h=120:color=0x8A5B44:t=fill,"      # sofa
    "drawbox=x=80:y=170:w=60:h=40:color=0xC9743F:t=fill,"        # cushion
    "drawbox=x=430:y=40:w=170:h=190:color=0xBFE0F5:t=fill,"      # window
    "drawbox=x=350:y=210:w=70:h=110:color=0x3E7A46:t=fill,"      # plant
    "drawbox=x=40:y=300:w=560:h=60:color=0xA58B6A:t=fill,"       # floor
    "noise=alls=30:allf=t+u"                                      # real texture
)

FILTERS: dict[str, str] = {
    # A floor plan: white page, hard thin lines, no colour anywhere.
    "floor_plan": (
        "color=c=0xF6F4F0:s=640x360,"
        "drawbox=x=40:y=26:w=560:h=308:color=0x202020:t=3,"
        "drawbox=x=40:y=180:w=300:h=3:color=0x202020:t=fill,"
        "drawbox=x=340:y=26:w=3:h=160:color=0x202020:t=fill,"
        "drawbox=x=150:y=180:w=3:h=154:color=0x202020:t=fill"
    ),
    # An unfurnished room: two flat planes and nothing in them.
    "empty_room": (
        "color=c=0xEDEAE4:s=640x360,"
        "drawbox=y=250:w=640:h=110:color=0xD8D0C4:t=fill"
    ),
    # A room shot at night with one small warm patch.
    "dark_room": (
        "color=c=0x14120F:s=640x360,"
        "drawbox=x=420:y=60:w=90:h=140:color=0x3A3128:t=fill"
    ),
    # Furniture under sheeting: colourless, bright, glinting on the folds.
    "plastic": (
        "color=c=0xCFCFCF:s=640x360,"
        "drawbox=x=90:y=150:w=420:h=170:color=0xDEDEDE:t=fill,"
        "drawbox=x=120:y=160:w=8:h=150:color=0xFFFFFF:t=fill,"
        "drawbox=x=230:y=160:w=6:h=150:color=0xFCFCFC:t=fill,"
        "drawbox=x=360:y=160:w=7:h=150:color=0xFFFFFF:t=fill"
    ),
    # A living room that is actually worth cutting to.
    "furnished": ROOM,
    # The same room with a large warm-toned subject filling the middle.
    "pet_on_sofa": ROOM + ",drawbox=x=200:y=90:w=240:h=180:color=0xC98F72:t=fill",
}


@pytest.fixture(scope="module")
def footage(tmp_path_factory) -> dict[str, str]:
    """Render every fixture once, as a real MP4."""

    directory = tmp_path_factory.mktemp("visual-fixtures")
    rendered: dict[str, str] = {}
    for name, filter_chain in FILTERS.items():
        path = directory / f"{name}.mp4"
        subprocess.run(
            [ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi", "-i", filter_chain,
             "-t", "2.0", "-r", "24", "-pix_fmt", "yuv420p", str(path)],
            check=True,
        )
        rendered[name] = str(path)
    return rendered


def analyze(footage: dict[str, str], name: str, query: str = "", narration: str = "",
            caption: str = "", tags: tuple[str, ...] = ()):
    """Run the real analyzer over real frames of one fixture."""

    clip = StockClip(
        provider="local", provider_id=name, download_url=footage[name],
        width=640, height=360, duration=2.0, query=query,
        description=caption, tags=list(tags),
    )
    clip.local_path = footage[name]
    analyzer = VisualAnalyzer(frames_per_clip=3)
    analysis = analyzer.analyze_clip(
        clip, query=query, narration=narration,
        metadata_flags=metadata_visual_flags(clip, query),
    )
    clip.visual = analysis.to_dict()
    clip.visual_semantic_match = analysis.semantic_match
    return clip, analysis


# ---------------------------------------------------------------------------
# 1. A floor plan is not footage of a room
# ---------------------------------------------------------------------------

def test_a_floor_plan_is_recognised_from_its_pixels(footage):
    _, analysis = analyze(footage, "floor_plan", query="interior design")
    assert analysis.analyzed
    assert analysis.frame_count == 3
    assert analysis.flags["floor_plan_or_document"] >= REJECT_CONFIDENCE
    assert analysis.rejected
    assert "floor_plan_or_document" in analysis.reject_reason


def test_a_floor_plan_never_illustrates_wall_and_trim_painting(footage):
    """The 45 second failure: an architectural drawing over painting advice."""

    clip, analysis = analyze(
        footage, "floor_plan",
        query="painted trim matching the wall color",
        narration="Paint the trim the same color as the walls.",
        # Exactly the kind of caption that got it through run 6.
        caption="modern interior design living room",
    )
    assert analysis.rejected
    assert rank_with_vision([clip]) == []


def test_a_caption_alone_would_still_have_let_the_floor_plan_through(footage):
    """The point of the whole module: metadata says this clip is fine."""

    clip = StockClip(
        provider="pexels", provider_id="1", download_url="http://x/y.mp4",
        width=1920, height=1080, duration=12.0,
        description="modern interior design living room",
    )
    assert metadata_visual_flags(clip) == {}


# ---------------------------------------------------------------------------
# 2. Plastic-covered furniture is not premium
# ---------------------------------------------------------------------------

def test_furniture_covered_in_plastic_is_not_premium(footage):
    """The 90 second failure."""

    clip, analysis = analyze(
        footage, "plastic",
        query="styled living room sofa",
        caption="sofa covered with plastic sheeting",
    )
    assert analysis.flags["plastic_covered_furniture"] >= PENALTY_CONFIDENCE
    assert not analysis.is_premium_visual
    assert analysis.premium_visual_score < 0.4


def test_the_caption_and_the_pixels_compound_into_a_rejection(footage):
    """Neither signal rejects alone; agreeing, they do.

    This is the mechanism that makes weak evidence useful instead of noisy.
    """

    without_caption = analyze(footage, "plastic", query="sofa")[1]
    with_caption = analyze(
        footage, "plastic", query="sofa", caption="furniture covered with plastic"
    )[1]
    assert without_caption.flags["plastic_covered_furniture"] < REJECT_CONFIDENCE
    assert with_caption.flags["plastic_covered_furniture"] > (
        without_caption.flags["plastic_covered_furniture"]
    )
    assert with_caption.rejected


# ---------------------------------------------------------------------------
# 3. Empty rooms
# ---------------------------------------------------------------------------

def test_a_mostly_empty_room_triggers_the_empty_room_penalty(footage):
    """The 85 and 95 second failures."""

    _, analysis = analyze(footage, "empty_room", query="cozy styled living room")
    assert analysis.flags["empty_room"] >= PENALTY_CONFIDENCE
    assert not analysis.is_premium_visual


def test_an_empty_room_is_rejected_once_the_caption_agrees(footage):
    _, analysis = analyze(
        footage, "empty_room", query="living room",
        caption="empty apartment with no furniture",
    )
    assert analysis.rejected


def test_a_dark_room_is_flagged_from_its_luminance(footage):
    _, analysis = analyze(footage, "dark_room", query="evening living room")
    assert analysis.flags["dark_scene"] >= REJECT_CONFIDENCE
    assert analysis.brightness < 60


# ---------------------------------------------------------------------------
# 4. A pet or a person as the subject
# ---------------------------------------------------------------------------

def test_a_pet_dominant_shot_is_downranked_against_the_same_room(footage):
    """The 55 second failure: a dog on a sofa, attractive and off-topic."""

    query = "styled living room with a sofa"
    narration = "Choose a sofa that leaves the floor visible around it."
    pet, pet_analysis = analyze(
        footage, "pet_on_sofa", query=query, narration=narration,
        caption="dog relaxing on a sofa by the window",
    )
    room, room_analysis = analyze(footage, "furnished", query=query, narration=narration)

    assert pet_analysis.flags.get("dominant_pet_or_person", 0) >= PENALTY_CONFIDENCE
    assert room_analysis.premium_visual_score > pet_analysis.premium_visual_score

    ordered = rank_with_vision([pet, room])
    assert ordered, "the clean room must survive"
    assert ordered[0].provider_id == "furnished"


def test_a_furnished_room_is_premium(footage):
    _, analysis = analyze(footage, "furnished", query="styled living room")
    assert analysis.is_premium_visual
    assert not analysis.rejected
    assert analysis.interior_likeness > 0.6


# ---------------------------------------------------------------------------
# 5 and 6. Causal promise alignment on the written paragraph
# ---------------------------------------------------------------------------

BIGGER = detect_promise("Small Living Room Tricks That Make Your Space Look Bigger")

MEASURE_WITHOUT_REASON = (
    "Measure the room before you buy anything. Measure before buying furniture "
    "because returns are expensive and nobody enjoys carrying a sofa back down "
    "the stairs."
)
MEASURE_WITH_REASON = (
    "Measure the room before you buy anything. Measure before buying furniture "
    "because oversized pieces consume visible floor area, narrow the pathways "
    "and make a small room feel cramped."
)


def test_measuring_without_a_perceived_space_reason_fails_the_causal_check():
    result = score_paragraph(MEASURE_WITHOUT_REASON, BIGGER)
    assert not result.passed
    assert result.score == 0.0
    assert "never states the outcome" in result.explain()


def test_the_same_idea_with_an_oversized_furniture_explanation_passes():
    result = score_paragraph(MEASURE_WITH_REASON, BIGGER)
    assert result.passed
    assert result.score == 1.0
    assert "furniture_scale" in result.mechanisms


def test_the_ceiling_light_idea_is_repaired_with_the_lighting_mechanism():
    """Run 6's first idea. Valid, but the script never said why."""

    text = (
        "Do not center the ceiling light by default. A single fitting in the "
        "middle of the ceiling is the builder's choice, not a designer's."
    )
    assert not score_paragraph(text, BIGGER).passed
    repaired = repair_text(text, BIGGER)
    assert repaired is not None
    assert "boundaries" in repaired or "walls" in repaired
    assert score_paragraph(repaired, BIGGER).score >= PASS_THRESHOLD


def test_every_mechanism_can_explain_itself():
    """A repair is only possible if the explanation itself passes the test."""

    from vidfactory.title_alignment import PROMISES

    for promise in PROMISES:
        if not promise.mechanisms or not promise.rescue_signals:
            continue
        for mechanism in promise.mechanisms:
            for sentence in mechanism.explanations:
                assert (
                    score_paragraph(sentence, promise).score >= PASS_THRESHOLD
                ), f"{promise.key}/{mechanism.name}: {sentence}"


def test_repairs_rotate_through_alternate_phrasings():
    """Six identical sentences in one video is the template-like writing we
    are trying to get rid of."""

    used: dict[str, int] = {}
    text = "Choose fewer, larger pieces instead of several small ones."
    first = repair_text(text, BIGGER, used=used)
    second = repair_text(text, BIGGER, used=used)
    assert first and second and first != second


def test_a_generated_script_explains_every_item(monkeypatch):
    from vidfactory.script_generator import generate_script
    from vidfactory.topic_engine import TopicEngine

    topic = TopicEngine().from_user_input(
        "Small Living Room Tricks That Make Your Space Look Bigger"
    )
    script = generate_script(topic, duration_minutes=6.0)
    assert script.causal.results
    assert script.causal_promise_alignment_score >= PASS_THRESHOLD
    assert min(script.section_alignment_scores) >= PASS_THRESHOLD
    for result in script.causal.results:
        assert result.explain()


# ---------------------------------------------------------------------------
# 7. Relevance outranks beauty
# ---------------------------------------------------------------------------

def _scored(name: str, semantic: float, likeness: float, premium: float) -> StockClip:
    clip = StockClip(
        provider="pexels", provider_id=name, download_url="http://x/y.mp4",
        width=1920, height=1080, duration=12.0,
    )
    clip.score_dimensions = {
        "novelty": 1.0, "resolution": 1.0, "orientation": 1.0,
        "duration": 1.0, "quality": 1.0,
    }
    clip.visual = {
        "analyzed": True, "semantic_match": semantic, "interior_likeness": likeness,
        "premium_visual_score": premium, "flags": {}, "rejected": False,
    }
    return clip


def test_a_plain_relevant_clip_outranks_a_beautiful_unrelated_one():
    relevant = _scored("relevant", semantic=0.86, likeness=0.62, premium=0.60)
    gorgeous = _scored("gorgeous", semantic=0.32, likeness=0.95, premium=0.95)
    ordered = rank_with_vision([gorgeous, relevant])
    assert [c.provider_id for c in ordered] == ["relevant", "gorgeous"]


def test_a_clip_that_does_not_show_the_narration_is_dropped():
    ordered = rank_with_vision(
        [_scored("off_topic", semantic=0.05, likeness=0.9, premium=0.9)],
        VisualRankingSettings(min_semantic=0.28),
    )
    assert ordered == []


def test_semantic_weight_dominates_the_breakdown():
    clip = _scored("x", semantic=1.0, likeness=1.0, premium=1.0)
    _, breakdown = visual_score(clip)
    assert breakdown["visual_semantic"] > breakdown["visual_subject"]
    assert breakdown["visual_subject"] > breakdown["visual_quality"]
    assert breakdown["visual_quality"] > breakdown["novelty"]
    assert breakdown["novelty"] > breakdown["technical"]


# ---------------------------------------------------------------------------
# 8. Sampling, expectations and the report
# ---------------------------------------------------------------------------

def test_frames_are_sampled_across_the_clip_not_from_its_first_second():
    positions = sample_positions(10.0, 3)
    assert positions[0] > 0
    assert positions[-1] < 10.0
    assert positions == sorted(positions)
    assert positions[-1] - positions[0] > 5.0


def test_frames_come_from_the_real_video(footage):
    frames = sample_frames(video=footage["furnished"], duration=2.0, count=3)
    assert len(frames) == 3
    assert all(f.ok for f in frames)
    # Different timestamps of a noisy clip are not byte-identical.
    assert len({f.pixels for f in frames}) > 1


def test_provider_stills_are_preferred_over_downloading_the_video(footage):
    """Three JPEGs beat transferring a video to find out it is unusable."""

    stills = [footage["furnished"]] * 3
    frames = sample_frames(video=None, stills=stills, count=3)
    assert len(frames) >= 1


def test_narration_selects_a_visual_expectation():
    names = [e.name for e in match_expectations(
        "Paint the trim the same color as the walls"
    )]
    assert "wall_and_trim_paint" in names
    assert "kitchen" not in names


def test_the_editorial_report_carries_the_new_visual_metrics(footage):
    clip, _ = analyze(footage, "furnished", query="styled living room")

    class _Result:
        def __init__(self, clip):
            self.clip = clip

    class _Shot:
        clip_key = "local:furnished"
        scene_id = "s1"
        duration = 4.0

    class _Plan:
        shots = [_Shot()]
        reused_keys: list[str] = []

    class _Script:
        title_idea_alignment = 1.0
        promise_key = "bigger"
        rejected_ideas: list[str] = []

    from vidfactory.causal_alignment import CausalReport, CausalResult

    causal = CausalReport(
        promise_key="bigger",
        results=[CausalResult(index=1, heading="1. x", score=0.9)],
    )
    report = build_report(
        shot_plan=_Plan(), clips=[_Result(clip)], scenes=[], script=_Script(),
        visual_stats={"model": "pixel-statistics", "frames": 3, "seconds": 0.4},
        causal=causal,
    )
    payload = json.loads(json.dumps(report.to_dict()))
    for key in (
        "visual_semantic_match_average",
        "low_relevance_clip_count",
        "visual_analysis_model",
        "visual_analysis_frame_count",
        "causal_promise_alignment_score",
        "section_alignment_scores",
    ):
        assert key in payload, key
    assert payload["visual_analysis_model"] == "pixel-statistics"
    assert payload["visual_analysis_frame_count"] == 3
    assert payload["section_alignment_scores"] == [0.9]


def test_premium_ratio_requires_both_the_caption_and_the_pixels(footage):
    """A clip whose caption says "interior" but whose frames say "floor plan"
    must not count towards the premium ratio."""

    clip, _ = analyze(
        footage, "floor_plan",
        query="living room", caption="modern interior design living room",
    )
    clip.premium = {"is_premium": True}

    class _Result:
        def __init__(self, clip):
            self.clip = clip

    class _Plan:
        shots: list = []
        reused_keys: list = []

    class _Script:
        title_idea_alignment = 1.0
        promise_key = "bigger"
        rejected_ideas: list = []

    report = build_report(
        shot_plan=_Plan(), clips=[_Result(clip)], scenes=[], script=_Script()
    )
    assert report.metrics["premium_visual_ratio"] == 0.0
    assert report.metrics["floor_plan_clip_count"] == 1
