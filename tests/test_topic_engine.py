"""Topic generation, similarity detection and duplicate rejection."""

from __future__ import annotations

import random

import pytest

from vidfactory.knowledge import ALL_CATEGORIES, normalize_category
from vidfactory.topic_engine import (
    Topic,
    TopicEngine,
    is_too_similar,
    similarity,
    slugify,
)


def test_identical_titles_are_maximally_similar():
    assert similarity("25 Small Living Room Ideas", "25 Small Living Room Ideas") == 1.0


def test_only_the_number_differs_is_still_a_duplicate():
    score = similarity("25 Small Living Room Ideas", "30 Small Living Room Ideas")
    assert score > 0.9


def test_unrelated_titles_score_low():
    score = similarity(
        "25 Small Living Room Ideas", "20 Farmhouse Kitchen Mistakes You Should Avoid"
    )
    assert score < 0.3


def test_superset_title_is_detected_as_similar():
    score = similarity(
        "Small Living Room Ideas", "Small Living Room Ideas For Renters On A Budget"
    )
    assert score > 0.5


def test_is_too_similar_reports_the_closest_match():
    history = ["20 Cozy Bedroom Ideas", "25 Small Living Room Ideas"]
    rejected, closest, score = is_too_similar("30 Small Living Room Ideas", history, 0.62)
    assert rejected is True
    assert closest == "25 Small Living Room Ideas"
    assert score >= 0.62


def test_not_too_similar_when_below_threshold():
    rejected, _, _ = is_too_similar("15 Bathroom Storage Ideas", ["25 Modern Kitchen Ideas"], 0.62)
    assert rejected is False


def test_generated_topics_are_unique_over_many_runs():
    engine = TopicEngine(history=[], similarity_threshold=0.62, rng=random.Random(11))
    titles: list[str] = []
    for _ in range(40):
        topic = engine.generate()
        rejected, closest, score = is_too_similar(topic.title, titles, 0.62)
        assert not rejected, f"{topic.title!r} duplicates {closest!r} ({score})"
        titles.append(topic.title)
        engine.history.append(topic.title)
    assert len(set(titles)) == 40


def test_generation_respects_existing_history():
    history = ["25 Small Living Room Ideas That Make Any Space Look Bigger"]
    engine = TopicEngine(history=history, similarity_threshold=0.5, rng=random.Random(3))
    topic = engine.generate(category="living rooms")
    rejected, _, _ = is_too_similar(topic.title, history, 0.5)
    assert not rejected


def test_generated_topic_has_a_real_category():
    engine = TopicEngine(rng=random.Random(5))
    topic = engine.generate()
    assert topic.category in ALL_CATEGORIES
    assert topic.item_count >= 3
    assert topic.slug


def test_user_topic_is_parsed():
    engine = TopicEngine()
    topic = engine.from_user_input("  20 Bedroom Decorating Mistakes You Should Avoid  ")
    assert topic.title == "20 Bedroom Decorating Mistakes You Should Avoid"
    assert topic.category == "bedrooms"
    assert topic.angle == "mistakes"
    assert topic.item_count == 20
    assert topic.source == "manual"


def test_user_topic_without_a_number_gets_one():
    topic = TopicEngine().from_user_input("Cozy Bedroom Ideas")
    assert topic.item_count >= 5


def test_empty_user_topic_is_rejected():
    with pytest.raises(ValueError):
        TopicEngine().from_user_input("   ")


def test_duplicate_manual_topic_can_be_rejected():
    engine = TopicEngine(history=["25 Small Living Room Ideas"], similarity_threshold=0.5)
    with pytest.raises(ValueError, match="similar"):
        engine.from_user_input("30 Small Living Room Ideas", allow_duplicate=False)


def test_duplicate_manual_topic_is_allowed_by_default():
    engine = TopicEngine(history=["25 Small Living Room Ideas"], similarity_threshold=0.5)
    topic = engine.from_user_input("30 Small Living Room Ideas")
    assert topic.title == "30 Small Living Room Ideas"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("25 Small Living Room Ideas", "living rooms"),
        ("20 Ways To Make Your Home Look More Expensive", "expensive look"),
        ("30 Cozy Bedroom Ideas", "bedrooms"),
        ("25 Small Kitchen Ideas", "kitchens"),
        ("25 Smart Storage Ideas For Small Homes", "storage"),
        ("20 Scandinavian Design Rules", "scandinavian design"),
    ],
)
def test_category_detection(title, expected):
    assert normalize_category(title) == expected


def test_slugify():
    assert slugify("25 Small Living Room Ideas!") == "25-small-living-room-ideas"
    assert slugify("") == "topic"


def test_topic_round_trips_to_dict():
    topic = Topic(title="20 Cozy Bedroom Ideas", category="bedrooms")
    payload = topic.to_dict()
    assert payload["slug"] == "20-cozy-bedroom-ideas"
    assert payload["keywords"]
