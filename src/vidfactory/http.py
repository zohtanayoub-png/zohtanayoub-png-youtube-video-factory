"""Shared HTTP helpers: retries, exponential backoff, timeouts, streaming.

External services fail. One failed request must never take down a twenty
minute render, so everything network-facing goes through here.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

from .logging_utils import get_logger

log = get_logger("HTTP")

DEFAULT_USER_AGENT = "vidfactory/1.0 (+https://github.com/) home-decor-video-factory"
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    """Raised when a request fails after every retry."""


def _sleep_for(attempt: int, base: float, retry_after: str | None = None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except (TypeError, ValueError):
            pass
    # Exponential backoff with jitter so parallel jobs do not resonate.
    return min(base * (2 ** attempt) + random.uniform(0, 0.4), 60.0)


def request_json(
    url: str,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    retries: int = 3,
    timeout: float = 30.0,
    backoff: float = 1.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """GET a JSON document with retries and exponential backoff."""

    http = session or requests
    all_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
    last_error: Exception | None = None

    for attempt in range(max(1, retries)):
        try:
            response = http.get(url, headers=all_headers, params=params, timeout=timeout)
            if response.status_code in RETRY_STATUS:
                delay = _sleep_for(attempt, backoff, response.headers.get("Retry-After"))
                log.warning(
                    "HTTP %s from %s; retrying in %.1fs",
                    response.status_code,
                    _host(url),
                    delay,
                )
                time.sleep(delay)
                last_error = HttpError(f"HTTP {response.status_code}")
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= retries - 1:
                break
            delay = _sleep_for(attempt, backoff)
            log.warning("Request to %s failed (%s); retrying in %.1fs", _host(url), exc, delay)
            time.sleep(delay)

    raise HttpError(f"Request to {_host(url)} failed: {last_error}")


def download_file(
    url: str,
    destination: str | Path,
    retries: int = 3,
    timeout: float = 120.0,
    max_bytes: int | None = None,
    backoff: float = 1.0,
    progress: Callable[[int], None] | None = None,
) -> Path:
    """Stream a file to disk with retries, size limit and partial cleanup."""

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(max(1, retries)):
        partial = target.with_suffix(target.suffix + ".part")
        try:
            with requests.get(
                url,
                stream=True,
                timeout=timeout,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            ) as response:
                response.raise_for_status()
                written = 0
                with open(partial, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if max_bytes and written > max_bytes:
                            raise HttpError(
                                f"file exceeded the {max_bytes / 1_000_000:.0f} MB limit"
                            )
                        handle.write(chunk)
                        if progress:
                            progress(written)
                if written == 0:
                    raise HttpError("empty response body")
            partial.replace(target)
            return target
        except Exception as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt >= retries - 1:
                break
            delay = _sleep_for(attempt, backoff)
            log.warning("Download from %s failed (%s); retrying in %.1fs", _host(url), exc, delay)
            time.sleep(delay)

    raise HttpError(f"Download from {_host(url)} failed: {last_error}")


def _host(url: str) -> str:
    """Return just the hostname so query strings (and keys) never reach logs."""

    try:
        from urllib.parse import urlparse

        return urlparse(url).hostname or "remote host"
    except Exception:  # pragma: no cover - defensive
        return "remote host"
