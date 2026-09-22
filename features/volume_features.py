"""
Volume features. "Unusual volume" is deliberately computed as a rolling
z-score / percentile rank against each stock's OWN recent history, not a
fixed multiple like "volume > 2x average" -- a fixed threshold is itself a
hardcoded rule wearing a disguise, and it doesn't adapt per-stock (a
stock that normally has huge volume swings shouldn't trip the same
threshold as a sleepy large-cap).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import VOLUME_ZSCORE_WINDOW


def add_volume_zscore(df: pd.DataFrame, window: int = VOLUME_ZSCORE_WINDOW) -> pd.DataFrame:
    df = df.copy()
    roll_mean = df["volume"].shift(1).rolling(window, min_periods=window // 2).mean()
    roll_std = df["volume"].shift(1).rolling(window, min_periods=window // 2).std()
    df["volume_zscore"] = (df["volume"] - roll_mean) / roll_std.replace(0, np.nan)
    df["volume_ratio_to_avg"] = df["volume"] / roll_mean.replace(0, np.nan)
    return df


def add_volume_percentile_rank(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Where today's volume ranks within its own trailing distribution
    (0-1). More robust to extreme outliers than a raw z-score alone."""
    df = df.copy()

    def _pct_rank(x: pd.Series) -> float:
        if len(x) < 2:
            return np.nan
        return (x.iloc[:-1] < x.iloc[-1]).mean()

    df["volume_percentile_rank"] = (
        df["volume"].rolling(window, min_periods=window // 2).apply(_pct_rank, raw=False)
    )
    return df


def add_obv(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    df = df.copy()
    direction = np.sign(df[price_col].diff()).fillna(0)
    df["obv"] = (direction * df["volume"]).cumsum()
    df["obv_change_5d"] = df["obv"].diff(5)
    return df


def add_delivery_pct_features(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Delivery % (from bhavcopy) proxies for genuine investment demand vs
    intraday/speculative churn -- a rising delivery % alongside a price
    rally is a meaningfully different signal than a rally on pure
    speculative volume."""
    df = df.copy()
    if "delivery_pct" not in df.columns:
        df["delivery_pct_zscore"] = np.nan
        return df
    roll_mean = df["delivery_pct"].shift(1).rolling(window, min_periods=window // 2).mean()
    roll_std = df["delivery_pct"].shift(1).rolling(window, min_periods=window // 2).std()
    df["delivery_pct_zscore"] = (df["delivery_pct"] - roll_mean) / roll_std.replace(0, np.nan)
    return df


def build_all_volume_features(single_symbol_df: pd.DataFrame) -> pd.DataFrame:
    df = single_symbol_df.sort_values("date").reset_index(drop=True)
    df = add_volume_zscore(df)
    df = add_volume_percentile_rank(df)
    df = add_obv(df)
    df = add_delivery_pct_features(df)
    return df
