"""YouTube upload support - no network, no credentials, no real uploads."""

from __future__ import annotations

import pytest

from vidfactory.youtube_upload import (
    UploadError,
    YouTubeCredentials,
    build_request_body,
    upload_video,
)


def test_credentials_require_all_three_secrets():
    with pytest.raises(UploadError, match="YOUTUBE_CLIENT_ID"):
        YouTubeCredentials.from_env({})


def test_credentials_load_from_env():
    creds = YouTubeCredentials.from_env(
        {
            "YOUTUBE_CLIENT_ID": "id-value",
            "YOUTUBE_CLIENT_SECRET": "secret-value",
            "YOUTUBE_REFRESH_TOKEN": "refresh-value",
        }
    )
    assert creds.client_id == "id-value"


def test_masked_credentials_never_expose_secrets():
    creds = YouTubeCredentials("client-id-1234", "supersecret", "refreshtoken")
    masked = creds.masked()
    assert "supersecret" not in str(masked)
    assert "refreshtoken" not in str(masked)
    assert masked["client_secret"] == "***"


def test_request_body_shape():
    body = build_request_body(
        {
            "title": "25 Small Living Room Ideas",
            "description": "A description",
            "tags": ["home decor", "living room ideas"],
            "category_id": "26",
            "privacy_status": "unlisted",
            "language": "en-US",
            "made_for_kids": False,
        }
    )
    assert body["snippet"]["title"] == "25 Small Living Room Ideas"
    assert body["snippet"]["categoryId"] == "26"
    assert body["status"]["privacyStatus"] == "unlisted"
    assert body["status"]["selfDeclaredMadeForKids"] is False


def test_request_body_truncates_long_fields():
    body = build_request_body({"title": "A" * 300, "description": "B" * 9000, "tags": ["x"] * 100})
    assert len(body["snippet"]["title"]) == 100
    assert len(body["snippet"]["description"]) == 5000
    assert len(body["snippet"]["tags"]) == 30


def test_invalid_privacy_status_is_rejected():
    with pytest.raises(UploadError):
        build_request_body({"title": "t", "privacy_status": "top-secret"})


def test_upload_requires_an_existing_file(tmp_path):
    with pytest.raises(UploadError, match="not found"):
        upload_video(
            tmp_path / "missing.mp4",
            {"title": "t"},
            credentials=YouTubeCredentials("a", "b", "c"),
        )


def test_upload_is_not_required_for_generation(config):
    """The default configuration must never attempt an upload."""
    assert config.get("youtube.upload_enabled") is False
    assert config.get("youtube.privacy_status") == "private"
