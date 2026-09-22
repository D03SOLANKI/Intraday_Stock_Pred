"""
Sector performance, broad market regime, and cross-sectional features.

Cross-sectional features (a stock's rank relative to its peer universe ON
THE SAME DAY) tend to matter a lot for a ranking task like this -- e.g.,
"volume z-score of 3.0" is more informative when you also know whether
EVERY stock had elevated volume that day (broad market event) or just this
one (idiosyncratic). All cross-sectional functions here operate on a single
day's cross-section across many symbols, called from feature_pipeline.py
after per-symbol features are computed for that day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_sector_relative_strength(
    stock_returns: pd.DataFrame, sector_returns: pd.DataFrame, ret_col: str = "ret_1d"
) -> pd.DataFrame:
    """
    stock_returns: ['symbol', 'date', 'sector', ret_col, ...]
    sector_returns: ['sector', 'date', ret_col] -- sector index return
    Returns stock_returns with an added `sector_relative_ret` column:
    the stock's return minus its own sector's return on the same day.
    """
    merged = stock_returns.merge(
        sector_returns.rename(columns={ret_col: "sector_ret"}),
        on=["sector", "date"], how="left",
    )
    merged["sector_relative_ret"] = merged[ret_col] - merged["sector_ret"]
    return merged


def add_market_regime_features(index_df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """
    Broad market regime features from a benchmark index (e.g., Nifty 50):
    trend direction, whether it's above/below its own moving averages, and
    realized volatility regime. Join this onto every stock-day by `date`.
    """
    df = index_df.sort_values("date").copy()
    df["index_ret_1d"] = df[price_col].pct_change()
    df["index_sma_50"] = df[price_col].rolling(50, min_periods=25).mean()
    df["index_sma_200"] = df[price_col].rolling(200, min_periods=100).mean()
    df["index_above_sma50"] = (df[price_col] > df["index_sma_50"]).astype(int)
    df["index_above_sma200"] = (df[price_col] > df["index_sma_200"]).astype(int)
    log_ret = np.log(df[price_col] / df[price_col].shift(1))
    df["index_realized_vol_20d"] = log_ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    return df[["date", "index_ret_1d", "index_above_sma50",
               "index_above_sma200", "index_realized_vol_20d"]]


def add_breadth_features(daily_cross_section: pd.DataFrame, ret_col: str = "ret_1d") -> pd.DataFrame:
    """
    Market breadth for a single day: fraction of stocks advancing,
    dispersion of returns. `daily_cross_section` is all symbols' rows for
    ONE date. Returns a one-row summary to be joined back onto that date.
    """
    advancing_frac = (daily_cross_section[ret_col] > 0).mean()
    return_dispersion = daily_cross_section[ret_col].std()
    return pd.Series({
        "date": daily_cross_section["date"].iloc[0],
        "pct_advancing": advancing_frac,
        "cross_sectional_return_dispersion": return_dispersion,
    })


def add_cross_sectional_ranks(daily_cross_section: pd.DataFrame,
                               rank_cols: list[str]) -> pd.DataFrame:
    """
    For a single day's cross-section (all stocks in one segment on one
    date), convert each raw feature into a percentile rank (0-1) relative
    to peers that day. This is often more predictive than the raw value,
    and naturally adapts across market regimes.
    """
    df = daily_cross_section.copy()
    for col in rank_cols:
        if col in df.columns:
            df[f"{col}_xs_rank"] = df[col].rank(pct=True)
    return df


def add_announcement_recency_feature(
    stock_df: pd.DataFrame, announcements_df: pd.DataFrame
) -> pd.DataFrame:
    """
    announcements_df: ['symbol', 'announcement_date', 'category'] from
    exchange filing feeds. Adds a `days_since_last_announcement` and a
    `had_announcement_yesterday` flag -- encoded as a feature for the model
    to weigh, not as a hardcoded rule that forces a prediction.
    """
    df = stock_df.sort_values("date").copy()
    ann = announcements_df[announcements_df["symbol"] == df["symbol"].iloc[0]].sort_values(
        "announcement_date"
    )
    if ann.empty:
        df["days_since_last_announcement"] = np.nan
        df["had_announcement_yesterday"] = 0
        return df

    ann_dates = ann["announcement_date"].to_numpy()

    def _days_since(d):
        prior = ann_dates[ann_dates < d]
        if len(prior) == 0:
            return np.nan
        return (pd.Timestamp(d) - pd.Timestamp(prior.max())).days

    df["days_since_last_announcement"] = df["date"].apply(_days_since)
    df["had_announcement_yesterday"] = (df["days_since_last_announcement"] == 1).astype(int)
    return df
