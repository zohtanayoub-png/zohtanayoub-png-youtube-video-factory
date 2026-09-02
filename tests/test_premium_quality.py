"""Regressions from the second production video review.

Two problems it exposed: the 60-30-10 colour rule survived a "look bigger"
title, and some selected footage was of people, dark rooms or empty spaces
rather than of interiors worth looking at.
"""

from __future__ import annotations

import pytest

from vidfactory.knowledge import tips_for
from vidfactory.ranking import (
    ClipRanker,
    RankingContext,
    dark_scene_penalty,
    empty_room_penalty,
    interior_relevance_score,
    people_dominance_penalty,
    premium_visual_report,
)
from vidfactory.script_generator import generate_script
from vidfactory.stock.base import StockClip
from vidfactory.title_alignment import (
    detect_promise,
    filter_aligned,
    score_alignment,
)
from vidfactory.topic_engine import TopicEngine


def clip(caption: str, query: str = "bright living room natural light") -> StockClip:
    return StockClip(
        provider="pexels", provider_id="1", download_url="https://x.invalid/a.mp4",
        width=1920, height=1080, duration=12.0, author="Someone",
        description=caption, query=query,
    )


# ==========================================================================
# 1. The 60-30-10 regression
# ==========================================================================

def test_the_sixty_thirty_ten_rule_is_rejected_for_look_bigger():
    """The exact case from the review."""

    promise = detect_promise("Small Living Room Tricks That Make Your Space Look Bigger")
    tip = next(t for t in tips_for(None) if "sixty thirty ten" in t["title"].lower())
    result = score_alignment(tip, promise)
    assert not result.aligned, result.explain()
    assert result.score == 0.0
    assert result.denied_by, "should be rejected as a generic design principle"


def test_it_stays_out_of_a_generated_script():
    topic = TopicEngine().from_user_input(
        "Small Living Room Tricks That Make Your Space Look Bigger"
    )
    script = generate_script(topic, duration_minutes=20.0)
    headings = " ".join(s.heading.lower() for s in script.items())
    assert "sixty thirty ten" in " ".join(
        r["title"].lower() for r in script.rejected_ideas
    ), "the rule should be recorded as rejected"
    assert "sixty thirty ten" not in headings
    assert "60 30 10" not in headings


def test_every_accepted_idea_names_a_causal_mechanism():
    promise = detect_promise("Make Any Space Look Bigger")
    kept, _ = filter_aligned(tips_for("small spaces"), promise)
    assert kept
    for tip in kept:
        assert score_alignment(tip, promise).mechanisms, tip["title"]


def test_real_space_tricks_are_still_accepted():
    promise = detect_promise("Make Any Space Look Bigger")
    for fragment in ("visible legs", "curtains close to the ceiling",
                     "continuous flooring", "do not block the window"):
        tip = next(t for t in tips_for(None) if fragment in t["title"].lower())
        assert score_alignment(tip, promise).aligned, tip["title"]


def test_an_ergonomic_tip_is_still_rejected():
    promise = detect_promise("Make Any Space Look Bigger")
    tip = next(t for t in tips_for(None) if "coffee table height" in t["title"].lower())
    assert not score_alignment(tip, promise).aligned


def test_a_generic_principle_is_rescued_when_it_states_the_outcome():
    """Trim painted to match the walls IS a space trick, and says so."""

    promise = detect_promise("Make Any Space Look Bigger")
    tip = next(t for t in tips_for(None) if "trim the same color" in t["title"].lower())
    assert score_alignment(tip, promise).aligned


@pytest.mark.parametrize("key", ["bigger", "expensive", "cozy", "brighter"])
def test_outcome_promises_all_require_a_mechanism(key):
    from vidfactory.title_alignment import PROMISES

    promise = next(p for p in PROMISES if p.key == key)
    assert promise.mechanisms, f"{key} must define direct mechanisms"


def test_the_pools_stay_large_enough_to_build_a_video():
    for title, category in (
        ("Make Any Space Look Bigger", "small spaces"),
        ("Make Your Home Look More Expensive", "expensive look"),
        ("Cozy Bedroom Ideas For A Warmer Home", "bedrooms"),
    ):
        kept, _ = filter_aligned(tips_for(category), detect_promise(title))
        assert len(kept) >= 12, (title, len(kept))


# ==========================================================================
# 2. Premium visual filtering
# ==========================================================================

@pytest.mark.parametrize(
    "caption",
    [
        "group of friends talking and laughing in a living room",
        "woman sitting on a sofa reading a book",
        "family having dinner in the dining room",
        "two people in a business meeting",
        "portrait of a smiling woman at home",
    ],
)
def test_people_dominant_footage_is_rejected(caption):
    report = premium_visual_report(clip(caption))
    assert report["is_people_dominant"], report
    assert not ClipRanker().is_eligible(clip(caption), RankingContext(query="living room"))


@pytest.mark.parametrize(
    "caption",
    ["empty unfurnished apartment with white walls",
     "bare room with no furniture", "vacant interior before moving in"],
)
def test_empty_rooms_are_rejected(caption):
    assert premium_visual_report(clip(caption))["is_empty_room"]
    assert not ClipRanker().is_eligible(clip(caption), RankingContext(query="living room"))


@pytest.mark.parametrize(
    "caption",
    ["dark room at night with dim light", "gloomy interior in darkness"],
)
def test_dark_footage_is_rejected(caption):
    assert premium_visual_report(clip(caption))["is_dark"]
    assert not ClipRanker().is_eligible(clip(caption), RankingContext(query="living room"))


def test_deliberate_warm_evening_footage_is_kept():
    """Cosy candlelight is the look this channel wants, not a dark room."""

    caption = "cozy living room with candles and a warm glow in the evening"
    report = premium_visual_report(clip(caption))
    assert not report["is_dark"]
    assert report["is_premium"]
    assert ClipRanker().is_eligible(clip(caption), RankingContext(query="living room"))


@pytest.mark.parametrize(
    "caption",
    ["modern office coworking space with desks", "hotel lobby reception area",
     "restaurant interior with tables"],
)
def test_non_home_spaces_are_rejected(caption):
    assert not ClipRanker().is_eligible(clip(caption), RankingContext(query="living room"))


@pytest.mark.parametrize(
    "caption",
    [
        "bright styled living room with natural light and plants",
        "beautiful scandinavian bedroom interior with linen bedding",
        "tall curtains by a sunlit window in a modern apartment",
        "wooden nightstand beside a bed in a bedroom",
    ],
)
def test_aspirational_interiors_are_kept(caption):
    report = premium_visual_report(clip(caption))
    assert report["is_premium"], report
    assert ClipRanker().is_eligible(clip(caption), RankingContext(query="living room"))


def test_word_boundaries_prevent_false_positives():
    """"sunlit" is not "unlit"; "nightstand" is not "night"."""

    assert dark_scene_penalty(clip("a sunlit window in the morning"))[0] == 0.0
    assert dark_scene_penalty(clip("wooden nightstand beside a bed"))[0] == 0.0
    assert dark_scene_penalty(clip("large dimensions of a room"))[0] == 0.0


def test_relevance_ignores_the_query_we_searched_with():
    """A clip must not look relevant just because of our own search string."""

    unrelated = clip("abstract motion graphic", query="bright living room natural light")
    assert unrelated.content_text == "abstract motion graphic"
    assert interior_relevance_score(unrelated, "bright living room natural light")[0] < 0.5


def test_a_clip_with_no_caption_is_treated_neutrally():
    bare = StockClip(provider="pexels", provider_id="9", download_url="u",
                     width=1920, height=1080, duration=10.0)
    report = premium_visual_report(bare)
    assert report["is_premium"]
    assert not report["is_people_dominant"]


def test_premium_footage_outranks_a_technically_better_people_clip():
    good = clip("bright styled living room natural light")
    good.provider_id = "good"
    people = clip("group of friends laughing on a sofa")
    people.provider_id = "people"
    people.width, people.height = 3840, 2160
    ranked = ClipRanker().rank([people, good], RankingContext(query="living room"))
    assert [c.provider_id for c in ranked] == ["good"]


def test_premium_enforcement_can_be_disabled_for_local_media():
    caption = "group of friends talking in a living room"
    context = RankingContext(query="living room", enforce_premium=False)
    assert ClipRanker().is_eligible(clip(caption), context)


def test_the_four_named_signals_are_all_reported():
    report = premium_visual_report(clip("bright living room"))
    for key in ("people_dominance_penalty", "empty_room_penalty",
                "dark_scene_penalty", "interior_relevance_score"):
        assert key in report
