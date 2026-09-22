"""Volatility and risk-oriented features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import BETA_WINDOW, VOLATILITY_WINDOWS


def add_realized_volatility(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    df = df.copy()
    log_ret = np.log(df[price_col] / df[price_col].shift(1))
    for w in VOLATILITY_WINDOWS:
        df[f"realized_vol_{w}d"] = log_ret.rolling(w, min_periods=w // 2).std() * np.sqrt(252)
    return df


def add_volatility_regime(df: pd.DataFrame, short_window: int = 10, long_window: int = 60) -> pd.DataFrame:
    """Ratio of short-term to long-term realized vol -- a proxy for whether
    the stock is currently in a volatility expansion or contraction phase,
    which conditions how much weight to give momentum signals."""
    df = df.copy()
    log_ret = np.log(df["close"] / df["close"].shift(1))
    short_vol = log_ret.rolling(short_window, min_periods=short_window // 2).std()
    long_vol = log_ret.rolling(long_window, min_periods=long_window // 2).std()
    df["vol_regime_ratio"] = short_vol / long_vol.replace(0, np.nan)
    return df


def add_beta_vs_index(stock_df: pd.DataFrame, index_df: pd.DataFrame,
                       window: int = BETA_WINDOW) -> pd.DataFrame:
    """
    Rolling beta of the stock's returns against the benchmark index
    (e.g., Nifty 50) returns. `index_df` must have ['date', 'close']
    for the benchmark, already aligned in time.
    """
    merged = stock_df.merge(
        index_df[["date", "close"]].rename(columns={"close": "index_close"}),
        on="date", how="left",
    ).sort_values("date")

    stock_ret = merged["close"].pct_change()
    index_ret = merged["index_close"].pct_change()

    cov = stock_ret.rolling(window).cov(index_ret)
    var = index_ret.rolling(window).var()
    merged["beta_vs_index"] = cov / var.replace(0, np.nan)
    return merged.drop(columns=["index_close"])


def build_all_volatility_features(single_symbol_df: pd.DataFrame) -> pd.DataFrame:
    df = single_symbol_df.sort_values("date").reset_index(drop=True)
    df = add_realized_volatility(df)
    df = add_volatility_regime(df)
    return df
