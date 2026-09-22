"""
Price-action, momentum, and technical indicator features.

CRITICAL RULE ENFORCED THROUGHOUT: every function here operates on data up
to and including day T only, and produces a feature "as of T" that is valid
to use for predicting T+1's return. Never call these on data that includes
T+1 or later. The feature_pipeline.py orchestrator is responsible for the
train/predict cutoff discipline; these functions just need pandas rolling
windows that, by construction, never look forward (`.rolling()` and
`.shift()` are inherently backward-looking as used here).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import (
    ATR_WINDOW, BOLLINGER_STD, BOLLINGER_WINDOW, MOVING_AVG_WINDOWS,
    PIVOT_LOOKBACK, RETURN_WINDOWS, RSI_WINDOW,
)


def add_return_features(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """df must be a single symbol's history sorted by date ascending."""
    df = df.copy()
    for w in RETURN_WINDOWS:
        df[f"ret_{w}d"] = df[price_col].pct_change(w)
    return df


def add_moving_average_features(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    df = df.copy()
    for w in MOVING_AVG_WINDOWS:
        ma = df[price_col].rolling(w, min_periods=max(2, w // 2)).mean()
        df[f"sma_{w}"] = ma
        df[f"dist_from_sma_{w}"] = (df[price_col] - ma) / ma
    return df


def add_rsi(df: pd.DataFrame, price_col: str = "close", window: int = RSI_WINDOW) -> pd.DataFrame:
    df = df.copy()
    delta = df[price_col].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window, min_periods=window).mean()
    avg_loss = loss.rolling(window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def add_macd(df: pd.DataFrame, price_col: str = "close",
             fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    df = df.copy()
    ema_fast = df[price_col].ewm(span=fast, adjust=False).mean()
    ema_slow = df[price_col].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    return df


def add_atr(df: pd.DataFrame, window: int = ATR_WINDOW) -> pd.DataFrame:
    df = df.copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(window, min_periods=window).mean()
    df["atr_pct"] = df["atr"] / df["close"]
    return df


def add_bollinger_features(df: pd.DataFrame, price_col: str = "close",
                            window: int = BOLLINGER_WINDOW, n_std: float = BOLLINGER_STD) -> pd.DataFrame:
    df = df.copy()
    sma = df[price_col].rolling(window, min_periods=window).mean()
    std = df[price_col].rolling(window, min_periods=window).std()
    upper = sma + n_std * std
    lower = sma - n_std * std
    df["bb_width"] = (upper - lower) / sma
    df["bb_position"] = (df[price_col] - lower) / (upper - lower).replace(0, np.nan)
    return df


def add_pivot_breakout_features(df: pd.DataFrame, price_col: str = "close",
                                 lookback: int = PIVOT_LOOKBACK) -> pd.DataFrame:
    """
    Distance from rolling resistance/support, computed using only data
    strictly BEFORE today (shift(1) before the rolling max/min) so today's
    own high/low can't leak into "how close to resistance was I today."
    """
    df = df.copy()
    rolling_high = df["high"].shift(1).rolling(lookback, min_periods=lookback // 2).max()
    rolling_low = df["low"].shift(1).rolling(lookback, min_periods=lookback // 2).min()
    df["dist_from_resistance"] = (rolling_high - df[price_col]) / df[price_col]
    df["dist_from_support"] = (df[price_col] - rolling_low) / df[price_col]
    df["broke_resistance"] = (df[price_col] > rolling_high).astype(int)
    df["broke_support"] = (df[price_col] < rolling_low).astype(int)
    return df


def add_gap_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    prev_close = df["close"].shift(1)
    df["gap_pct"] = (df["open"] - prev_close) / prev_close
    return df


def add_52week_features(df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    df = df.copy()
    window = 252
    roll_high = df[price_col].shift(1).rolling(window, min_periods=window // 2).max()
    roll_low = df[price_col].shift(1).rolling(window, min_periods=window // 2).min()
    df["dist_from_52w_high"] = (roll_high - df[price_col]) / roll_high
    df["dist_from_52w_low"] = (df[price_col] - roll_low) / roll_low
    return df


def build_all_price_features(single_symbol_df: pd.DataFrame) -> pd.DataFrame:
    """Convenience wrapper applying every price feature to one symbol's
    chronologically sorted history."""
    df = single_symbol_df.sort_values("date").reset_index(drop=True)
    df = add_return_features(df)
    df = add_moving_average_features(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_atr(df)
    df = add_bollinger_features(df)
    df = add_pivot_breakout_features(df)
    df = add_gap_features(df)
    df = add_52week_features(df)
    return df
