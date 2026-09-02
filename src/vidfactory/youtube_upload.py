"""Optional YouTube upload through the official YouTube Data API v3.

This is entirely optional: the video generator works with
``youtube.upload_enabled: false`` (the default) and never imports Google
libraries unless an upload is actually requested.

Credentials
-----------
Nothing is ever written to the repository. Three GitHub Secrets are used:

``YOUTUBE_CLIENT_ID``
``YOUTUBE_CLIENT_SECRET``
``YOUTUBE_REFRESH_TOKEN``

The refresh token is obtained once, locally, with
``python -m vidfactory.youtube_upload --authorize`` (see SETUP.md). Refresh
tokens are long-lived, so this is a one-time step, and the token never needs
to leave GitHub Secrets afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .logging_utils import get_logger

log = get_logger("YOUTUBE")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
VALID_PRIVACY = {"private", "unlisted", "public"}


class UploadError(RuntimeError):
    """Raised when an upload cannot be performed."""


@dataclass
class YouTubeCredentials:
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "YouTubeCredentials":
        environment = env if env is not None else os.environ
        missing = [
            name
            for name in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
            if not environment.get(name)
        ]
        if missing:
            raise UploadError(
                "Missing YouTube credentials: " + ", ".join(missing)
                + ". Add them as GitHub Secrets (see SETUP.md)."
            )
        return cls(
            client_id=environment["YOUTUBE_CLIENT_ID"],
            client_secret=environment["YOUTUBE_CLIENT_SECRET"],
            refresh_token=environment["YOUTUBE_REFRESH_TOKEN"],
        )

    def masked(self) -> dict[str, str]:
        """Safe representation for logging - never exposes the real values."""
        return {
            "client_id": f"***{self.client_id[-4:]}" if self.client_id else "",
            "client_secret": "***",
            "refresh_token": "***",
        }


def build_request_body(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Translate our metadata dict into the YouTube API request body."""

    privacy = str(metadata.get("privacy_status", "private")).lower()
    if privacy not in VALID_PRIVACY:
        raise UploadError(f"privacy_status must be one of {sorted(VALID_PRIVACY)}")

    tags = [str(t) for t in metadata.get("tags", [])][:30]
    return {
        "snippet": {
            "title": str(metadata.get("title", ""))[:100],
            "description": str(metadata.get("description", ""))[:5000],
            "tags": tags,
            "categoryId": str(metadata.get("category_id", "26")),
            "defaultLanguage": str(metadata.get("language", "en-US")),
            "defaultAudioLanguage": str(metadata.get("language", "en-US")),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": bool(metadata.get("made_for_kids", False)),
            "embeddable": True,
        },
    }


def upload_video(
    video_path: str | Path,
    metadata: Mapping[str, Any],
    credentials: YouTubeCredentials | None = None,
    subtitles_path: str | Path | None = None,
) -> str:
    """Upload one video and return its YouTube video ID."""

    path = Path(video_path)
    if not path.exists():
        raise UploadError(f"video file not found: {path}")

    creds = credentials or YouTubeCredentials.from_env()

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise UploadError(
            "YouTube upload needs the optional dependencies: "
            "pip install -r requirements-youtube.txt"
        ) from exc

    google_credentials = Credentials(
        token=None,
        refresh_token=creds.refresh_token,
        client_id=creds.client_id,
        client_secret=creds.client_secret,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    service = build("youtube", "v3", credentials=google_credentials, cache_discovery=False)

    body = build_request_body(metadata)
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")

    log.info("Uploading %s as %s", path.name, body["status"]["privacyStatus"])
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    last_reported = -10
    while response is None:
        status, response = request.next_chunk()
        if status:
            percent = int(status.progress() * 100)
            if percent - last_reported >= 10:
                log.info("Upload progress: %d%%", percent)
                last_reported = percent

    video_id = str((response or {}).get("id", ""))
    if not video_id:
        raise UploadError("YouTube did not return a video id")
    log.info("Uploaded: https://www.youtube.com/watch?v=%s", video_id)

    if subtitles_path and Path(subtitles_path).exists():
        try:
            _upload_captions(service, video_id, Path(subtitles_path))
        except Exception as exc:
            log.warning("Caption upload failed (the video itself is fine): %s", exc)

    return video_id


def _upload_captions(service: Any, video_id: str, srt_path: Path) -> None:
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(srt_path), mimetype="application/octet-stream", resumable=False)
    service.captions().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "language": "en",
                "name": "English",
                "isDraft": False,
            }
        },
        media_body=media,
    ).execute()
    log.info("Captions uploaded")


# ---------------------------------------------------------------------------
# One-time local authorization helper
# ---------------------------------------------------------------------------

def authorize(client_secrets_file: str, output: str | None = None) -> str:
    """Run the one-time OAuth flow locally and print the refresh token.

    Run this on your own machine once. The resulting refresh token goes into
    the ``YOUTUBE_REFRESH_TOKEN`` GitHub Secret; nothing is written to the
    repository.
    """

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise UploadError(
            "Install the optional dependencies first: pip install -r requirements-youtube.txt"
        ) from exc

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    refresh_token = credentials.refresh_token or ""
    if not refresh_token:
        raise UploadError(
            "Google did not return a refresh token. Revoke the app's access in your "
            "Google Account and run this again."
        )

    print("\n" + "=" * 70)
    print("Add these three values as GitHub repository secrets:")
    print("  YOUTUBE_CLIENT_ID      =", credentials.client_id)
    print("  YOUTUBE_CLIENT_SECRET  =", credentials.client_secret)
    print("  YOUTUBE_REFRESH_TOKEN  =", refresh_token)
    print("=" * 70)
    print("Do NOT commit these values to the repository.\n")

    if output:
        # Written only where the operator explicitly asks, never in the repo by default.
        Path(output).write_text(
            json.dumps({"refresh_token": refresh_token}, indent=2), encoding="utf-8"
        )
        print(f"Refresh token also written to {output} - keep this file private.")
    return refresh_token


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - interactive
    parser = argparse.ArgumentParser(description="YouTube upload helper")
    parser.add_argument("--authorize", metavar="CLIENT_SECRETS_JSON",
                        help="Run the one-time OAuth flow with a downloaded client_secrets.json")
    parser.add_argument("--out", help="Optional file to write the refresh token to (keep private)")
    args = parser.parse_args(argv)

    if args.authorize:
        authorize(args.authorize, args.out)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
