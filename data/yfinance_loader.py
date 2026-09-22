"""
Yahoo Finance loader (via yfinance). Used as:
  (a) a backup/cross-check against bhavcopy (Yahoo's adjusted close handles
      some corporate actions automatically, useful for sanity-checking the
      corporate_actions.py adjustment logic), and
  (b) a fallback when bhavcopy has gaps (exchange holidays not marked
      correctly, format changes, etc.)

NSE symbols on Yahoo need a ".NS" suffix (e.g., "ADANIGAS.NS").
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

from config.settings import YFINANCE_DIR
from data.loaders import MarketDataSource


class YFinanceLoader(MarketDataSource):
    def __init__(self, cache_dir: Path = YFINANCE_DIR, sleep_between_calls: float = 0.3):
        self.cache_dir = cache_dir
        self.sleep_between_calls = sleep_between_calls

    def fetch_ohlcv(self, symbols, start: date, end: date) -> pd.DataFrame:
        frames = []
        for symbol in symbols:
            try:
                df = self._fetch_one(symbol, start, end)
            except Exception as exc:  # noqa: BLE001
                print(f"[yfinance] skip {symbol}: {exc}")
                continue
            if not df.empty:
                frames.append(df)
            time.sleep(self.sleep_between_calls)

        if not frames:
            return pd.DataFrame(
                columns=["symbol", "date", "open", "high", "low", "close",
                         "volume", "delivery_pct", "source"]
            )
        return pd.concat(frames, ignore_index=True)

    def fetch_universe(self, as_of: date) -> pd.DataFrame:
        raise NotImplementedError(
            "yfinance has no reliable index-constituent history endpoint; "
            "use data/universe.py (which combines bhavcopy tradeable symbols "
            "with an external constituent-history source) instead."
        )

    def _fetch_one(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        yahoo_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        cache_path = self.cache_dir / f"{symbol}_{start}_{end}.parquet"
        if cache_path.exists():
            return pd.read_parquet(cache_path)

        raw = yf.download(
            yahoo_symbol, start=start, end=end,
            progress=False, auto_adjust=False,
        )
        if raw.empty:
            return pd.DataFrame()

        raw = raw.reset_index()
        # yfinance sometimes returns MultiIndex columns for single-ticker
        # requests depending on version; normalise defensively.
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]

        df = pd.DataFrame({
            "symbol": symbol,
            "date": pd.to_datetime(raw["Date"]).dt.date,
            "open": raw["Open"],
            "high": raw["High"],
            "low": raw["Low"],
            "close": raw["Close"],
            "volume": raw["Volume"],
            "delivery_pct": pd.NA,  # not available from yfinance
            "source": "yfinance",
        })
        df.to_parquet(cache_path, index=False)
        return df
