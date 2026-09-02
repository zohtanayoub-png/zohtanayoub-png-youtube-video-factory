"""Script generation (fallback engine) and scene planning."""

from __future__ import annotations

import re

import pytest

from vidfactory.knowledge import KNOWLEDGE, tips_for, total_tips
from vidfactory.scene_planner import (
    ScenePlanner,
    derive_queries,
    estimate_duration,
    group_sentences,
    plan_scenes,
    split_sentences,
)
from vidfactory.script_generator import (
    TemplateScriptEngine,
    generate_script,
    retitle_for_count,
)
from vidfactory.topic_engine import TopicEngine


# --------------------------------------------------------------------- script

def test_knowledge_base_is_substantial():
    assert total_tips() > 200
    assert len(KNOWLEDGE) >= 20


def test_every_tip_is_complete():
    for category, tips in KNOWLEDGE.items():
        for tip in tips:
            assert tip["title"], category
            assert len(tip["why"].split()) >= 12, tip["title"]
            assert len(tip["how"].split()) >= 10, tip["title"]
            assert len(tip["queries"]) >= 3, tip["title"]
            assert tip["tags"], tip["title"]


def test_template_engine_never_needs_a_network(topic):
    script = generate_script(topic, duration_minutes=10.0, engine="template")
    assert script.engine == "template"
    assert script.word_count > 500


def test_fallback_used_when_llm_unavailable(topic, monkeypatch):
    """`auto` with the LLM enabled must fall back rather than crash."""

    import vidfactory.script_generator as module

    def boom(*args, **kwargs):
        raise RuntimeError("no model on this runner")

    monkeypatch.setattr(module, "generate_script", module.generate_script)
    script = generate_script(
        topic,
        duration_minutes=5.0,
        engine="auto",
        llm_settings={"enabled": True, "model_repo": "does/not-exist", "model_file": "nope.gguf"},
    )
    assert script.word_count > 200
    assert script.sections


def test_script_has_intro_items_and_outro(script):
    kinds = [section.kind for section in script.sections]
    assert kinds[0] == "intro"
    assert kinds[-1] == "outro"
    assert kinds.count("intro") == 1
    assert kinds.count("outro") == 1
    assert len(script.items()) >= 3


def test_items_are_numbered_in_order(script):
    for position, section in enumerate(script.items(), start=1):
        assert section.index == position
        assert section.heading.startswith(f"{position}. ")


def test_no_duplicate_ideas_in_one_script(script):
    headings = [s.heading.split(". ", 1)[-1] for s in script.items()]
    assert len(headings) == len(set(headings))


@pytest.mark.parametrize("minutes", [1.0, 5.0, 10.0, 20.0])
def test_script_length_tracks_the_requested_duration(topic, minutes):
    script = generate_script(topic, duration_minutes=minutes, engine="template")
    estimated = script.estimated_seconds / 60.0
    assert estimated <= minutes * 1.35
    assert estimated >= minutes * 0.6


def test_longer_videos_produce_longer_scripts(topic):
    short = generate_script(topic, duration_minutes=5.0, engine="template")
    long = generate_script(topic, duration_minutes=20.0, engine="template")
    assert long.word_count > short.word_count * 1.8


def test_script_is_original_prose_not_a_bullet_list(script):
    assert "•" not in script.text
    assert not re.search(r"^\s*[-*]\s", script.text, flags=re.MULTILINE)
    assert "<|" not in script.text


def test_two_topics_do_not_produce_identical_scripts():
    engine = TopicEngine()
    a = generate_script(engine.from_user_input("25 Small Living Room Ideas"), 10.0)
    b = generate_script(engine.from_user_input("25 Cozy Bedroom Ideas"), 10.0)
    assert a.text != b.text
    assert a.sections[0].text != b.sections[0].text


def test_script_serializes(script):
    payload = script.to_dict()
    assert payload["title"]
    assert payload["word_count"] == script.word_count
    assert len(payload["sections"]) == len(script.sections)


@pytest.mark.parametrize(
    "title,count,expected",
    [
        ("25 Small Living Room Ideas", 25, "25 Small Living Room Ideas"),
        ("25 Small Living Room Ideas", 12, "12 Small Living Room Ideas"),
        ("25 Small Living Room Ideas", 1, "Small Living Room Ideas"),
        ("Cozy Bedroom Ideas", 8, "Cozy Bedroom Ideas"),
    ],
)
def test_retitle_for_count(title, count, expected):
    assert retitle_for_count(title, count) == expected


def test_no_ungrammatical_one_item_phrasing():
    topic = TopicEngine().from_user_input("5 Small Living Room Ideas")
    script = generate_script(topic, duration_minutes=0.8, engine="template")
    assert " 1 ideas" not in script.text
    assert " 1 minutes" not in script.text
    assert not script.title.startswith("1 ")


def test_item_count_is_capped_by_available_material():
    engine = TemplateScriptEngine()
    topic = TopicEngine().from_user_input("500 Bathroom Ideas")
    count = engine.plan_item_count(topic, 20.0, pool_size=len(tips_for("bathrooms")))
    assert count <= len(tips_for("bathrooms"))


# --------------------------------------------------------------------- scenes

def test_split_sentences():
    text = "Hang the curtains high. It works. Really!"
    assert split_sentences(text) == ["Hang the curtains high.", "It works.", "Really!"]


def test_split_sentences_handles_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_group_sentences_respects_the_word_budget():
    sentences = ["One two three four five."] * 10
    groups = group_sentences(sentences, max_words=10)
    assert all(len(g.split()) <= 12 for g in groups)
    assert " ".join(groups).count("One") == 10


def test_estimate_duration_scales_with_words():
    assert estimate_duration("one two three four five six seven eight nine ten") == pytest.approx(4.0)
    assert estimate_duration("word") >= 1.5


def test_scene_planning_covers_the_whole_script(script):
    scenes = plan_scenes(script)
    assert len(scenes) >= len(script.sections)
    joined = " ".join(scene.narration for scene in scenes)
    assert len(joined.split()) == script.word_count


def test_every_scene_has_queries_and_duration(script):
    for scene in plan_scenes(script):
        assert scene.primary_visual_query
        assert len(scene.queries) >= 2
        assert scene.estimated_duration > 0
        assert scene.scene_id


def test_scenes_are_not_all_the_same_query(script):
    queries = {scene.primary_visual_query for scene in plan_scenes(script)}
    assert len(queries) > 4


def test_queries_follow_the_narration_not_the_title():
    queries = derive_queries(
        "Floor to ceiling curtains can make a low room appear considerably taller.",
        "living rooms",
    )
    assert any("curtain" in q for q in queries)

    queries = derive_queries(
        "A rug that is too small can visually shrink your seating area.", "living rooms"
    )
    assert any("rug" in q for q in queries)


def test_tip_queries_lead_the_first_scene_of_an_item(script):
    scenes = plan_scenes(script)
    first_item = next(s for s in scenes if s.section_kind == "item" and s.scene_id.endswith("-00"))
    item_section = next(s for s in script.items() if s.index == first_item.section_index)
    assert first_item.primary_visual_query == item_section.tip["queries"][0].lower()


def test_scene_serializes(script):
    payload = plan_scenes(script)[0].to_dict()
    for key in ("scene_id", "narration", "estimated_duration", "primary_visual_query"):
        assert key in payload


def test_planner_word_budget_is_configurable(script):
    tight = ScenePlanner(max_words_per_scene=15).plan(script)
    loose = ScenePlanner(max_words_per_scene=60).plan(script)
    assert len(tight) > len(loose)
