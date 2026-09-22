"""
Orchestrates feature engineering across the full universe, enforcing the
leakage-safety discipline in one place rather than trusting every caller to
get it right:

  1. Per-symbol features (price/volume/volatility) are computed on that
     symbol's own chronological history using only backward-looking
     windows.
  2. Cross-sectional features (sector-relative, market breadth,
     percentile ranks vs peers) are computed PER DAY, using only that
     day's already-backward-looking per-symbol features -- never using
     tomorrow's cross-section.
  3. The final feature matrix for date T is guaranteed to use no
     information from T+1 onward. `labels.py` is the ONLY place T+1
     information is introduced, and only as the target column, kept in a
     separate DataFrame until explicitly joined for training.
"""

from __future__ import annotations

import pandas as pd

from features.price_features import build_all_price_features
from features.sector_market_features import (
    add_cross_sectional_ranks, add_market_regime_features,
    add_sector_relative_strength,
)
from features.volatility_features import build_all_volatility_features
from features.volume_features import build_all_volume_features

# Feature columns eligible for cross-sectional (peer-relative) ranking.
# Centralized here so it's easy to audit/extend.
CROSS_SECTIONAL_RANK_COLS = [
    "ret_1d", "ret_5d", "ret_20d", "volume_zscore", "volume_ratio_to_avg",
    "rsi", "atr_pct", "realized_vol_20d", "dist_from_resistance",
    "dist_from_52w_high",
]


def build_symbol_features(raw_symbol_df: pd.DataFrame) -> pd.DataFrame:
    """Apply all per-symbol feature families to one symbol's OHLCV history."""
    df = build_all_price_features(raw_symbol_df)
    df = build_all_volume_features(df)
    df = build_all_volatility_features(df)
    return df


def build_universe_features(
    raw_universe_df: pd.DataFrame,
    index_df: pd.DataFrame,
    sector_map: pd.DataFrame,
) -> pd.DataFrame:
    """
    raw_universe_df: long-format OHLCV for every symbol, columns
      ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume',
       'delivery_pct', 'segment', 'sector']
    index_df: benchmark index OHLCV (e.g., Nifty 50), ['date', 'close']
    sector_map: ['symbol', 'sector'] if not already present in raw_universe_df

    Returns a single feature matrix across all symbols and dates, with
    cross-sectional features computed within each (date, segment) group so
    a small-cap's "unusual volume" is judged against other small-caps, not
    against large-caps with structurally different volume profiles.
    """
    if "sector" not in raw_universe_df.columns:
        raw_universe_df = raw_universe_df.merge(sector_map, on="symbol", how="left")

    per_symbol_frames = []
    for symbol, grp in raw_universe_df.groupby("symbol"):
        feat = build_symbol_features(grp)
        feat["symbol"] = symbol
        # segment/sector are static-ish per symbol but carry them through
        for col in ("segment", "sector"):
            if col in grp.columns:
                feat[col] = grp[col].iloc[0]
        per_symbol_frames.append(feat)

    all_features = pd.concat(per_symbol_frames, ignore_index=True)

    # sector-relative strength (needs a sector-level return series first)
    sector_returns = (
        all_features.groupby(["sector", "date"])["ret_1d"].mean()
        .reset_index()
    )
    all_features = add_sector_relative_strength(all_features, sector_returns)

    # market regime features (from benchmark index), joined by date
    regime = add_market_regime_features(index_df)
    all_features = all_features.merge(regime, on="date", how="left")

    # cross-sectional peer ranks, computed within (date, segment)
    ranked_frames = []
    for (_, _), grp in all_features.groupby(["date", "segment"]):
        ranked_frames.append(add_cross_sectional_ranks(grp, CROSS_SECTIONAL_RANK_COLS))
    all_features = pd.concat(ranked_frames, ignore_index=True)

    return all_features.sort_values(["date", "segment", "symbol"]).reset_index(drop=True)
