"""Пакет интеграции с внешним API YTimes."""

from .api_client import Shop, YTimesAPIClient, YTimesAPIError

__all__ = [
    "Shop",
    "YTimesAPIClient",
    "YTimesAPIError",
]

