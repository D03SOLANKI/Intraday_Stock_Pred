"""
Abstract interface for market data sources. Every concrete loader
(bhavcopy, yfinance, or a future paid vendor) implements this interface so
the rest of the pipeline (features/models/validation) never needs to know
which source the data came from.

To add a paid vendor later (Kite Connect, TrueData, Global Datafeeds):
subclass MarketDataSource, implement fetch_ohlcv() and fetch_universe(),
and point pipeline/train_pipeline.py at the new class. Nothing else changes.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class OHLCVRecord:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    delivery_pct: float | None = None  # NSE-specific; not all sources provide this
    source: str = "unknown"


class MarketDataSource(abc.ABC):
    """Common interface every data adapter must implement."""

    @abc.abstractmethod
    def fetch_ohlcv(
        self, symbols: Iterable[str], start: date, end: date
    ) -> pd.DataFrame:
        """
        Return a long-format DataFrame with columns:
        ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume',
         'delivery_pct', 'source']
        Must NOT forward-fill across gaps silently -- missing sessions
        should remain missing so downstream code can decide how to handle
        them (important for avoiding artificial smoothing that leaks
        information).
        """
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_universe(self, as_of: date) -> pd.DataFrame:
        """
        Return the point-in-time set of tradeable symbols as of `as_of`,
        with columns ['symbol', 'segment']. This must reflect what was
        actually listed/liquid on that date -- not today's list applied
        retroactively -- to avoid survivorship bias.
        """
        raise NotImplementedError

    def name(self) -> str:
        return self.__class__.__name__
