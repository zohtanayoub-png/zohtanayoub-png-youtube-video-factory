"""Tagged, secret-safe logging.

Output looks like::

    12:03:41 [TOPIC]  Selected: 25 Small Living Room Ideas ...
    12:04:02 [SCRIPT] 3,242 words generated

Any value that looks like a credential is redacted before it reaches a log
handler, so API keys can never leak into GitHub Actions logs.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Iterable

_SECRET_ENV_HINTS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CLIENT_ID",
    "REFRESH",
)

_TOKEN_PATTERNS = (
    re.compile(r"(api[_-]?key=)([^&\s]+)", re.IGNORECASE),
    re.compile(r"(authorization:\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(access_token=)([^&\s]+)", re.IGNORECASE),
)


def _collect_secrets() -> list[str]:
    secrets: list[str] = []
    for name, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        upper = name.upper()
        if any(hint in upper for hint in _SECRET_ENV_HINTS):
            secrets.append(value)
    return secrets


class RedactingFilter(logging.Filter):
    """Replaces known secret values (and token-looking strings) with ``***``."""

    def __init__(self, extra_secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = [s for s in (*_collect_secrets(), *extra_secrets) if s]

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, "***REDACTED***")
        for pattern in _TOKEN_PATTERNS:
            text = pattern.sub(r"\1***REDACTED***", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D102
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = self.redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class _TagFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D102
        tag = getattr(record, "tag", None) or record.name.split(".")[-1].upper()
        record.tag = f"[{tag}]"
        return super().format(record)


_CONFIGURED = False


def setup_logging(verbose: bool = False, logfile: str | None = None) -> None:
    """Install the tagged formatter + redaction filter on the root logger."""

    global _CONFIGURED
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = _TagFormatter("%(asctime)s %(tag)-10s %(message)s", datefmt="%H:%M:%S")
    redactor = RedactingFilter()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    stream.addFilter(redactor)
    root.addHandler(stream)

    if logfile:
        os.makedirs(os.path.dirname(os.path.abspath(logfile)) or ".", exist_ok=True)
        file_handler = logging.FileHandler(logfile, encoding="utf-8")
        file_handler.setFormatter(fmt)
        file_handler.addFilter(redactor)
        root.addHandler(file_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    _CONFIGURED = True


class TaggedLogger:
    """Small wrapper so call sites read ``log.info("...")`` with a fixed tag."""

    def __init__(self, tag: str) -> None:
        self.tag = tag.upper()
        self._logger = logging.getLogger(f"vidfactory.{self.tag.lower()}")

    def _log(self, level: int, msg: str, *args: object) -> None:
        self._logger.log(level, msg, *args, extra={"tag": self.tag})

    def debug(self, msg: str, *args: object) -> None:
        self._log(logging.DEBUG, msg, *args)

    def info(self, msg: str, *args: object) -> None:
        self._log(logging.INFO, msg, *args)

    def warning(self, msg: str, *args: object) -> None:
        self._log(logging.WARNING, msg, *args)

    def error(self, msg: str, *args: object) -> None:
        self._log(logging.ERROR, msg, *args)


def get_logger(tag: str) -> TaggedLogger:
    if not _CONFIGURED:
        setup_logging()
    return TaggedLogger(tag)
