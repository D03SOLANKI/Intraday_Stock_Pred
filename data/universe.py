"""
Point-in-time market-cap segment membership.

THE SURVIVORSHIP BIAS PROBLEM, explicitly:
If you take today's Nifty Midcap 150 list and use it to pull 5 years of
history, every stock that got delisted, merged, acquired, or dropped out of
the index (often BECAUSE it performed badly) is silently excluded from
training data. The model then learns from a universe that's biased toward
"stocks that turned out fine," which inflates backtested performance in a
way that will NOT hold in live prediction (where failing stocks are very
much still in the tradeable universe).

FREE-TIER REALITY:
NSE does not offer a free bulk API for historical index constituent lists.
Two honest workarounds, both implemented below, ranked by quality:

  1. `load_archived_constituent_snapshots()`: NSE publishes periodic index
     factsheets (e.g., niftyindices.com) with as-of-date PDFs/CSVs that get
     rebalanced ~semi-annually. Manually download a handful of historical
     snapshots (e.g., one per rebalance date over your training period) and
     point this function at the directory -- it interpolates: a stock is
     considered "in segment X" from the snapshot date it appears until the
     next snapshot where it doesn't. This is the honest free-tier method.
  2. `approximate_by_market_cap_rank()`: FALLBACK ONLY. Computes market cap
     from bhavcopy close * shares outstanding (if you have a shares-
     outstanding series) and buckets stocks into segments by rank each day.
     This is NOT what the official indices use (they have additional
     eligibility/liquidity screens) but avoids survivorship bias since it's
     computed fresh from raw data at each point in time, with no dependency
     on which stocks "made it" into today's index list.

Recommendation: use (1) when you can get even a few real snapshots; use (2)
purely as a bootstrap while you gather better constituent history. Note
this clearly in any research writeup -- segment labels are an approximation
until a paid vendor's clean constituent-history feed is wired in.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from config.settings import SEGMENT_INDEX_MAP, UNIVERSE_DIR


def load_archived_constituent_snapshots(snapshot_dir: Path = UNIVERSE_DIR) -> pd.DataFrame:
    """
    Expects CSV files named like `NIFTY_MIDCAP_150_2024-04-01.csv` with at
    least a `symbol` column, one file per (segment, rebalance-date) snapshot
    you've manually collected. Returns a long DataFrame:
    ['symbol', 'segment', 'effective_from', 'effective_to'].

    Returns an empty DataFrame (with correct columns) if no snapshots are
    found yet -- callers should fall back to approximate_by_market_cap_rank
    in that case and log a warning, not fail silently.
    """
    records = []
    files = sorted(Path(snapshot_dir).glob("*.csv"))
    if not files:
        return pd.DataFrame(columns=["symbol", "segment", "effective_from", "effective_to"])

    parsed = []
    for f in files:
        segment = _infer_segment_from_filename(f.name)
        snap_date = _infer_date_from_filename(f.name)
        if segment is None or snap_date is None:
            continue
        df = pd.read_csv(f)
        df["segment"] = segment
        df["snapshot_date"] = snap_date
        parsed.append(df[["symbol", "segment", "snapshot_date"]])

    if not parsed:
        return pd.DataFrame(columns=["symbol", "segment", "effective_from", "effective_to"])

    all_snaps = pd.concat(parsed, ignore_index=True).sort_values("snapshot_date")

    for (symbol, segment), grp in all_snaps.groupby(["symbol", "segment"]):
        dates = sorted(grp["snapshot_date"].unique())
        for i, d in enumerate(dates):
            effective_to = dates[i + 1] if i + 1 < len(dates) else date.max
            records.append({
                "symbol": symbol,
                "segment": segment,
                "effective_from": d,
                "effective_to": effective_to,
            })

    return pd.DataFrame(records)


def approximate_by_market_cap_rank(
    bhavcopy_df: pd.DataFrame,
    shares_outstanding: pd.DataFrame,
    as_of: date,
    large_cap_cutoff_rank: int = 100,
    mid_cap_cutoff_rank: int = 250,
) -> pd.DataFrame:
    """
    FALLBACK ONLY -- see module docstring. `shares_outstanding` must be a
    DataFrame with ['symbol', 'shares_outstanding'] (as-of `as_of`, itself
    a data-sourcing task you'll need a source for -- e.g., BSE/NSE company
    filings, screener.in scraping, or a vendor). Rank cutoffs are the
    standard AMFI-style definitions (top 100 = large, next 150 = mid, rest
    = small) and are passed as parameters, not buried constants.
    """
    day_prices = bhavcopy_df[bhavcopy_df["date"] == as_of][["symbol", "close"]]
    merged = day_prices.merge(shares_outstanding, on="symbol", how="inner")
    merged["market_cap"] = merged["close"] * merged["shares_outstanding"]
    merged = merged.sort_values("market_cap", ascending=False).reset_index(drop=True)
    merged["rank"] = merged.index + 1

    def _segment(rank: int) -> str:
        if rank <= large_cap_cutoff_rank:
            return "large_cap"
        if rank <= mid_cap_cutoff_rank:
            return "mid_cap"
        return "small_cap"

    merged["segment"] = merged["rank"].apply(_segment)
    return merged[["symbol", "segment", "market_cap", "rank"]]


def get_segment_as_of(universe_snapshots: pd.DataFrame, symbol: str, as_of: date) -> str | None:
    """Look up a symbol's segment membership at a specific point in time."""
    match = universe_snapshots[
        (universe_snapshots["symbol"] == symbol)
        & (universe_snapshots["effective_from"] <= as_of)
        & (universe_snapshots["effective_to"] > as_of)
    ]
    if match.empty:
        return None
    return match.iloc[0]["segment"]


def _infer_segment_from_filename(filename: str) -> str | None:
    upper = filename.upper()
    for segment, index_name in SEGMENT_INDEX_MAP.items():
        if index_name.replace(" ", "_") in upper.replace(" ", "_"):
            return segment
    return None


def _infer_date_from_filename(filename: str) -> date | None:
    import re

    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if not match:
        return None
    return pd.to_datetime(match.group(1)).date()
