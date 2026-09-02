"""Provider registry - the single place new stock sources are wired in."""

from __future__ import annotations

import os
from typing import Any, Mapping

from ..logging_utils import get_logger
from .base import StockProvider
from .local import LocalProvider
from .pexels import PexelsProvider
from .pixabay import PixabayProvider

log = get_logger("STOCK")

PROVIDER_CLASSES: dict[str, type[StockProvider]] = {
    PexelsProvider.name: PexelsProvider,
    PixabayProvider.name: PixabayProvider,
    LocalProvider.name: LocalProvider,
}

ENV_KEYS: dict[str, str] = {
    "pexels": "PEXELS_API_KEY",
    "pixabay": "PIXABAY_API_KEY",
}


def build_providers(
    sources_config: Mapping[str, Any], env: Mapping[str, str] | None = None
) -> list[StockProvider]:
    """Instantiate every provider that is both enabled and usable."""

    environment = env if env is not None else os.environ
    providers: list[StockProvider] = []

    for name, provider_class in PROVIDER_CLASSES.items():
        if not sources_config.get(name, False):
            continue
        api_key = environment.get(ENV_KEYS.get(name, ""), "") if name in ENV_KEYS else None
        options: dict[str, Any] = {}
        if name == "local" and sources_config.get("local_directory"):
            options["directory"] = sources_config["local_directory"]
        provider = provider_class(api_key=api_key, **options)
        if not provider.available:
            log.warning(
                "%s is enabled but unusable (missing credentials or media) - skipping",
                name,
            )
            continue
        providers.append(provider)

    if providers:
        log.info("Active providers: %s", ", ".join(p.name for p in providers))
    else:
        log.error("No usable stock providers. Set PEXELS_API_KEY or enable sources.local")
    return providers
