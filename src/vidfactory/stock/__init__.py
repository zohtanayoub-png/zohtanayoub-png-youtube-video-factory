"""Stock footage source adapters.

Every provider implements :class:`~vidfactory.stock.base.StockProvider` so new
legal sources can be added without touching the rest of the pipeline.
"""

from .base import StockClip, StockProvider, ProviderError
from .registry import build_providers, PROVIDER_CLASSES

__all__ = [
    "StockClip",
    "StockProvider",
    "ProviderError",
    "build_providers",
    "PROVIDER_CLASSES",
]
