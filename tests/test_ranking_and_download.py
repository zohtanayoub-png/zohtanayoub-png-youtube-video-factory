"""Clip scoring, selection and duplicate prevention."""

from __future__ import annotations

import pytest

from vidfactory.downloader import ClipDownloader, content_hash
from vidfactory.ranking import (
    ClipRanker,
    RankingContext,
    diversify,
    score_duration,
    score_novelty,
    score_orientation,
    score_relevance,
    score_resolution,
)
from vidfactory.stock.base import StockClip


def clip(**kwargs) -> StockClip:
    defaults = dict(
        provider="pexels",
        provider_id="1",
        download_url="https://example.invalid/a.mp4",
        width=1920,
        height=1080,
        duration=12.0,
        author="Author",
        file_size=8_000_000,
        query="modern living room interior",
        tags=["living", "room", "modern"],
    )
    defaults.update(kwargs)
    return StockClip(**defaults)


# ------------------------------------------------------------------ dimensions

def test_relevance_rewards_matching_words():
    matching = score_relevance(clip(tags=["curtains", "window"]), "curtains window")
    unrelated = score_relevance(clip(tags=["kitchen", "sink"], query="kitchen"), "curtains window")
    assert matching > unrelated


def test_resolution_prefers_1080p_and_punishes_small():
    assert score_resolution(clip(width=1920, height=1080)) > score_resolution(
        clip(width=1280, height=720)
    )
    assert score_resolution(clip(width=640, height=360)) < 0.2


def test_4k_is_not_rewarded_over_1080p():
    assert score_resolution(clip(width=3840, height=2160)) <= score_resolution(
        clip(width=1920, height=1080)
    )


def test_orientation_rejects_vertical():
    assert score_orientation(clip(width=1080, height=1920)) == 0.0
    assert score_orientation(clip(width=1920, height=1080)) == pytest.approx(1.0)


def test_duration_prefers_clips_long_enough_for_a_shot():
    assert score_duration(clip(duration=12.0)) > score_duration(clip(duration=2.0))
    assert score_duration(clip(duration=0.0)) > 0


def test_novelty_prefers_unused_clips():
    assert score_novelty(clip(), use_count=0) == 1.0
    assert score_novelty(clip(), use_count=1, days_since_use=5, cooldown_days=45) == 0.0
    assert score_novelty(clip(), use_count=1, days_since_use=200, cooldown_days=45) > 0.0


# ---------------------------------------------------------------------- ranker

def test_the_best_clip_is_not_simply_the_first_result():
    weak = clip(provider_id="weak", width=1280, height=720, duration=5.0, tags=["office"])
    strong = clip(provider_id="strong", width=1920, height=1080, duration=14.0,
                  tags=["living", "room", "curtains"])
    ranker = ClipRanker()
    context = RankingContext(query="curtains living room", keywords=["curtains"])
    ranked = ranker.rank([weak, strong], context)
    assert ranked[0].provider_id == "strong"


def test_low_resolution_clips_are_rejected_outright():
    ranker = ClipRanker()
    context = RankingContext(query="living room", min_width=1280, min_height=720)
    assert ranker.rank([clip(width=640, height=360, duration=10)], context) == []


def test_vertical_clips_are_rejected():
    ranker = ClipRanker()
    context = RankingContext(query="living room")
    assert ranker.rank([clip(width=1080, height=1920)], context) == []


def test_very_short_clips_are_rejected():
    ranker = ClipRanker()
    context = RankingContext(query="living room", min_source_seconds=5.0, min_shot_seconds=4.0)
    assert ranker.rank([clip(duration=1.0)], context) == []


def test_clip_on_cooldown_scores_lower_than_a_fresh_one():
    ranker = ClipRanker()
    context = RankingContext(
        query="living room",
        history={"pexels:used": (2, 3.0)},
        cooldown_days=45,
    )
    used, _ = ranker.score(clip(provider_id="used"), context)
    fresh, _ = ranker.score(clip(provider_id="fresh"), context)
    assert fresh > used


def test_overused_clips_are_penalised():
    ranker = ClipRanker(max_uses_per_clip=2)
    context = RankingContext(query="living room", history={"pexels:1": (5, 400.0)})
    score, breakdown = ranker.score(clip(), context)
    assert "overuse_penalty" in breakdown


def test_already_selected_clips_are_penalised():
    ranker = ClipRanker()
    context = RankingContext(query="living room", already_selected={"pexels:1"})
    _, breakdown = ranker.score(clip(), context)
    assert breakdown["repeat_penalty"] < 0


def test_scores_are_bounded_by_the_weights():
    ranker = ClipRanker()
    score, _ = ranker.score(clip(), RankingContext(query="modern living room interior"))
    assert 0 <= score <= 100


def test_ranking_is_ordered_best_first():
    clips = [
        clip(provider_id=str(i), width=1280 + i * 160, height=720 + i * 90, duration=6 + i)
        for i in range(5)
    ]
    ranked = ClipRanker().rank(clips, RankingContext(query="living room"))
    scores = [c.score for c in ranked]
    assert scores == sorted(scores, reverse=True)


def test_diversify_avoids_sibling_uploads():
    clips = [clip(provider_id=str(1000 + i), author="Same Person", score=90 - i) for i in range(6)]
    chosen = diversify(clips, limit=3)
    assert len({c.provider_id for c in chosen}) == 3


def test_diversify_tops_up_when_filters_are_too_strict():
    clips = [clip(provider_id=str(1000 + i), author="Same", score=90 - i) for i in range(4)]
    assert len(diversify(clips, limit=4)) == 4


# ------------------------------------------------------------------ downloader

def test_content_hash_detects_identical_files(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    c = tmp_path / "c.bin"
    a.write_bytes(b"x" * 5000)
    b.write_bytes(b"x" * 5000)
    c.write_bytes(b"y" * 5000)
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash(c)
    assert content_hash(tmp_path / "missing") == ""


def test_downloader_rejects_a_non_video(tmp_path, monkeypatch):
    downloader = ClipDownloader(tmp_path / "work")
    target = downloader.target_path(clip())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"not a video at all" * 100)
    assert downloader.fetch(clip()) is None
    assert downloader.failures == 1


def test_downloader_rejects_duplicate_content(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")
    from vidfactory.testassets import make_test_clip

    source = make_test_clip(tmp_path / "src.mp4", seconds=6, width=1280, height=720)
    downloader = ClipDownloader(tmp_path / "work", min_width=1280, min_height=720, min_seconds=3)

    first = downloader.fetch(clip(provider_id="a", local_path=str(source)))
    assert first is not None
    second = downloader.fetch(clip(provider_id="b", local_path=str(source)))
    assert second is None


def test_downloader_rejects_low_resolution_files(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")
    from vidfactory.testassets import make_test_clip

    source = make_test_clip(tmp_path / "small.mp4", seconds=6, width=640, height=360)
    downloader = ClipDownloader(tmp_path / "work", min_width=1280, min_height=720)
    assert downloader.fetch(clip(provider_id="small", local_path=str(source))) is None


def test_downloader_handles_a_missing_local_file(tmp_path):
    downloader = ClipDownloader(tmp_path / "work")
    assert downloader.fetch(clip(local_path=str(tmp_path / "nope.mp4"))) is None
