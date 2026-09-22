"""
NSE Bhavcopy loader.

Bhavcopy is NSE's official daily EOD report (all listed securities: OHLCV,
delivery %). It's free but has a few real-world gotchas handled here:
  - File format/URL has changed multiple times over the years (old .zip CSV
    format vs newer UDiFF format). This loader targets the current UDiFF
    "Sec_bhavdata_full" CSV format and isolates the URL logic so it's the
    one place to fix if NSE changes format again.
  - NSE's site blocks generic requests without browser-like headers and
    occasionally rate-limits; retries with backoff are built in.
  - No corporate-action adjustment is applied here -- that happens in
    data/corporate_actions.py, deliberately kept separate so raw data stays
    auditable.
"""

from __future__ import annotations

import io
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from config.settings import BHAVCOPY_DIR
from data.loaders import MarketDataSource

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/octet-stream,*/*",
}

# NSE UDiFF daily bhavcopy URL pattern (subject to change -- centralised here
# deliberately). Format: https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
BHAVCOPY_URL_TEMPLATE = (
    "https://archives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
)

COLUMN_RENAME_MAP = {
    "TckrSymb": "symbol",
    "TradDt": "date",
    "OpnPric": "open",
    "HghPric": "high",
    "LwPric": "low",
    "ClsPric": "close",
    "TtlTradgVol": "volume",
    "DELIV_PER": "delivery_pct",
    "SctySrs": "series",
}


class BhavcopyLoader(MarketDataSource):
    def __init__(self, cache_dir: Path = BHAVCOPY_DIR, max_retries: int = 3):
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(NSE_HEADERS)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def fetch_ohlcv(self, symbols, start: date, end: date) -> pd.DataFrame:
        frames = []
        for day in self._trading_day_range(start, end):
            try:
                df = self._load_single_day(day)
            except Exception as exc:  # noqa: BLE001 -- log & continue; a
                # single missing/holiday day should not kill the whole run.
                print(f"[bhavcopy] skip {day}: {exc}")
                continue
            frames.append(df)

        if not frames:
            return pd.DataFrame(
                columns=["symbol", "date", "open", "high", "low", "close",
                         "volume", "delivery_pct", "source"]
            )

        full = pd.concat(frames, ignore_index=True)
        symbol_set = set(symbols)
        if symbol_set:
            full = full[full["symbol"].isin(symbol_set)]
        return full.reset_index(drop=True)

    def fetch_universe(self, as_of: date) -> pd.DataFrame:
        """
        Bhavcopy alone doesn't carry index-membership info. This returns
        every symbol that traded (series == 'EQ') on `as_of` as a raw
        tradeable universe -- segment tagging (large/mid/small) must be
        layered on via data/universe.py using index constituent data.
        """
        df = self._load_single_day(as_of)
        eq = df[df.get("series", "EQ") == "EQ"] if "series" in df.columns else df
        return pd.DataFrame({"symbol": eq["symbol"].unique()})

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _load_single_day(self, day: date) -> pd.DataFrame:
        cache_path = self.cache_dir / f"{day.isoformat()}.parquet"
        if cache_path.exists():
            return pd.read_parquet(cache_path)

        raw = self._download(day)
        df = self._parse(raw, day)
        df.to_parquet(cache_path, index=False)
        return df

    def _download(self, day: date) -> bytes:
        url = BHAVCOPY_URL_TEMPLATE.format(yyyymmdd=day.strftime("%Y%m%d"))
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, timeout=20)
                resp.raise_for_status()
                return resp.content
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"failed to download bhavcopy for {day}: {last_exc}")

    def _parse(self, raw_bytes: bytes, day: date) -> pd.DataFrame:
        import zipfile

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            with zf.open(csv_name) as f:
                df = pd.read_csv(f)

        df = df.rename(columns=COLUMN_RENAME_MAP)
        keep = [c for c in
                ["symbol", "date", "open", "high", "low", "close",
                 "volume", "delivery_pct", "series"]
                if c in df.columns]
        df = df[keep].copy()
        df["date"] = pd.to_datetime(df.get("date", day)).dt.date
        df["source"] = "bhavcopy"
        numeric_cols = ["open", "high", "low", "close", "volume", "delivery_pct"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    @staticmethod
    def _trading_day_range(start: date, end: date):
        d = start
        while d <= end:
            if d.weekday() < 5:  # skip weekends; exchange holidays are
                                  # handled by _load_single_day's try/except
                yield d
            d += timedelta(days=1)
