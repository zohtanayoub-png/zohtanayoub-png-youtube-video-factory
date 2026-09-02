"""Provider API response parsing, with mocked HTTP - no credentials needed."""

from __future__ import annotations

import json

import pytest

from vidfactory.stock import build_providers
from vidfactory.stock.base import ProviderError, StockClip
from vidfactory.stock.local import LocalProvider
from vidfactory.stock.pexels import PexelsProvider
from vidfactory.stock.pixabay import PixabayProvider

PEXELS_RESPONSE = {
    "page": 1,
    "videos": [
        {
            "id": 1234567,
            "width": 3840,
            "height": 2160,
            "duration": 21,
            "url": "https://www.pexels.com/video/example-1234567/",
            "image": "https://images.pexels.com/videos/1234567/preview.jpg",
            "user": {"name": "Jane Doe", "url": "https://www.pexels.com/@janedoe"},
            "video_files": [
                {"id": 1, "quality": "sd", "file_type": "video/mp4", "width": 640,
                 "height": 360, "link": "https://player.vimeo.com/x/360.mp4", "file_size": 900000},
                {"id": 2, "quality": "hd", "file_type": "video/mp4", "width": 1920,
                 "height": 1080, "link": "https://player.vimeo.com/x/1080.mp4", "file_size": 9000000},
                {"id": 3, "quality": "uhd", "file_type": "video/mp4", "width": 3840,
                 "height": 2160, "link": "https://player.vimeo.com/x/2160.mp4", "file_size": 40000000},
            ],
        },
        {
            "id": 7654321,
            "width": 1920,
            "height": 1080,
            "duration": 9,
            "url": "https://www.pexels.com/video/example-7654321/",
            "user": {"name": "Sam Smith", "url": "https://www.pexels.com/@samsmith"},
            "video_files": [
                {"id": 4, "file_type": "video/mp4", "width": 1920, "height": 1080,
                 "link": "https://player.vimeo.com/y/1080.mp4", "file_size": 7000000}
            ],
        },
    ],
}

PIXABAY_RESPONSE = {
    "total": 2,
    "hits": [
        {
            "id": 999,
            "pageURL": "https://pixabay.com/videos/id-999/",
            "duration": 15,
            "user": "someone",
            "user_id": 42,
            "tags": "living room, sofa, interior",
            "videos": {
                "large": {"url": "https://cdn.pixabay.com/large.mp4", "width": 1920,
                          "height": 1080, "size": 12000000},
                "medium": {"url": "https://cdn.pixabay.com/medium.mp4", "width": 1280,
                           "height": 720, "size": 5000000},
            },
        },
        {
            "id": 1000,
            "pageURL": "https://pixabay.com/videos/id-1000/",
            "duration": 6,
            "user": "other",
            "user_id": 43,
            "tags": "kitchen, modern",
            "videos": {"tiny": {"url": "https://cdn.pixabay.com/tiny.mp4", "width": 640,
                                "height": 360, "size": 400000}},
        },
    ],
}


# --------------------------------------------------------------------- pexels

def test_pexels_parses_a_real_shaped_response():
    clips = PexelsProvider.parse(PEXELS_RESPONSE, query="living room")
    assert len(clips) == 2
    first = clips[0]
    assert first.provider == "pexels"
    assert first.provider_id == "1234567"
    assert first.author == "Jane Doe"
    assert first.duration == 21
    assert first.query == "living room"
    assert first.license_name.startswith("Pexels")


def test_pexels_prefers_the_best_file_under_4k():
    clips = PexelsProvider.parse(PEXELS_RESPONSE)
    assert clips[0].width == 3840
    assert clips[0].download_url.endswith("2160.mp4")


def test_pexels_skips_entries_without_usable_files():
    payload = {"videos": [{"id": 1, "video_files": [{"file_type": "video/webm", "width": 1920}]}]}
    assert PexelsProvider.parse(payload) == []


def test_pexels_handles_empty_and_malformed_payloads():
    assert PexelsProvider.parse({}) == []
    assert PexelsProvider.parse({"videos": None}) == []


def test_pexels_requires_a_key():
    provider = PexelsProvider(api_key="")
    assert provider.available is False
    with pytest.raises(ProviderError):
        provider.search("living room")


def test_pexels_search_uses_landscape_orientation(monkeypatch):
    captured = {}

    def fake_request_json(url, headers=None, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = dict(params or {})
        captured["headers"] = dict(headers or {})
        return PEXELS_RESPONSE

    monkeypatch.setattr("vidfactory.stock.pexels.request_json", fake_request_json)
    provider = PexelsProvider(api_key="test-key")
    clips = provider.search("cozy bedroom", per_page=15)
    assert len(clips) == 2
    assert captured["params"]["orientation"] == "landscape"
    assert captured["params"]["per_page"] == 15
    assert captured["headers"]["Authorization"] == "test-key"


# -------------------------------------------------------------------- pixabay

def test_pixabay_parses_a_real_shaped_response():
    clips = PixabayProvider.parse(PIXABAY_RESPONSE, query="living room")
    assert len(clips) == 2
    assert clips[0].provider == "pixabay"
    assert clips[0].width == 1920
    assert "sofa" in clips[0].tags
    assert clips[1].width == 640


def test_pixabay_picks_the_largest_rendition():
    clips = PixabayProvider.parse(PIXABAY_RESPONSE)
    assert clips[0].download_url.endswith("large.mp4")


def test_pixabay_handles_empty_payload():
    assert PixabayProvider.parse({}) == []


def test_pixabay_search_enforces_minimum_per_page(monkeypatch):
    captured = {}

    def fake_request_json(url, params=None, **kwargs):
        captured["params"] = dict(params or {})
        return PIXABAY_RESPONSE

    monkeypatch.setattr("vidfactory.stock.pixabay.request_json", fake_request_json)
    PixabayProvider(api_key="k").search("x", per_page=1)
    assert captured["params"]["per_page"] >= 3


# ---------------------------------------------------------------------- local

def test_local_provider_reads_a_folder(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg is required to build test clips")
    from vidfactory.testassets import make_test_clip

    make_test_clip(tmp_path / "cozy-living-room-sofa.mp4", seconds=6, width=1280, height=720)
    make_test_clip(tmp_path / "bright-kitchen-counter.mp4", seconds=6, width=1280, height=720)

    provider = LocalProvider(directory=tmp_path)
    assert provider.available is True
    results = provider.search("living room sofa", per_page=5)
    assert results
    assert results[0].provider_id == "cozy-living-room-sofa"
    assert results[0].local_path


def test_local_provider_is_unavailable_for_an_empty_folder(tmp_path):
    assert LocalProvider(directory=tmp_path / "nothing").available is False


# ------------------------------------------------------------------- registry

def test_registry_skips_providers_without_credentials():
    providers = build_providers({"pexels": True, "pixabay": True, "local": False}, env={})
    assert providers == []


def test_registry_builds_configured_providers():
    providers = build_providers(
        {"pexels": True, "pixabay": False, "local": False},
        env={"PEXELS_API_KEY": "abc"},
    )
    assert [p.name for p in providers] == ["pexels"]


def test_search_many_tolerates_a_failing_query(monkeypatch):
    provider = PexelsProvider(api_key="key")
    calls = {"n": 0}

    def flaky(query, per_page=20, **kwargs):
        calls["n"] += 1
        if query == "bad":
            raise RuntimeError("boom")
        return PexelsProvider.parse(PEXELS_RESPONSE, query)

    monkeypatch.setattr(provider, "search", flaky)
    clips = provider.search_many(["bad", "good"], per_page=5)
    assert calls["n"] == 2
    assert len(clips) == 2


def test_stock_clip_helpers():
    clip = StockClip("pexels", "1", "u", 1920, 1080, 10.0)
    assert clip.key == "pexels:1"
    assert clip.is_landscape is True
    assert round(clip.aspect_ratio, 3) == round(16 / 9, 3)
    assert json.dumps(clip.to_dict())
