"""
Evaluation metrics for both the walk-forward backtest and live scoring.
Every metric here should be interpreted RELATIVE to the naive baselines
(models/linear_models.py) -- an information coefficient of 0.05 sounds
unimpressive in isolation but may be meaningfully better than a baseline's
0.01, or it may not beat it at all. Always report both.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def information_coefficient(predicted: pd.Series, actual: pd.Series) -> float:
    """Spearman rank correlation between predicted and actual forward
    returns -- the standard quant metric for ranking quality, robust to
    outliers unlike Pearson correlation on raw returns."""
    mask = predicted.notna() & actual.notna()
    if mask.sum() < 3:
        return np.nan
    corr, _ = spearmanr(predicted[mask], actual[mask])
    return corr


def top_n_hit_rate(predicted: pd.Series, actual: pd.Series, n: int = 3) -> float:
    """Of the top-N ranked stocks, what fraction had positive actual
    forward returns."""
    top_idx = predicted.sort_values(ascending=False).head(n).index
    return float((actual.loc[top_idx] > 0).mean())


def top_n_avg_return(predicted: pd.Series, actual: pd.Series, n: int = 3) -> float:
    top_idx = predicted.sort_values(ascending=False).head(n).index
    return float(actual.loc[top_idx].mean())


def calibration_table(predicted_probs: pd.Series, actual_outcomes: pd.Series, n_bins: int = 10) -> pd.DataFrame:
    """Bins predicted probabilities and compares to actual observed
    frequency in each bin -- a well-calibrated model's bins should track
    the diagonal (predicted ~= observed)."""
    df = pd.DataFrame({"pred": predicted_probs, "actual": actual_outcomes}).dropna()
    df["bin"] = pd.qcut(df["pred"], n_bins, duplicates="drop")
    return df.groupby("bin", observed=True).agg(
        predicted_avg=("pred", "mean"),
        actual_rate=("actual", "mean"),
        n=("actual", "size"),
    ).reset_index()


def evaluate_split(
    predictions_by_model: dict[str, pd.Series], actual_returns: pd.Series,
    actual_top_gainer_flag: pd.Series | None = None, top_n: int = 3,
) -> pd.DataFrame:
    """
    Evaluate every model's predictions (including naive baselines) on one
    walk-forward test split, side by side, so ML-vs-baseline comparison is
    always front and center in any report.
    """
    rows = []
    for model_name, preds in predictions_by_model.items():
        row = {
            "model": model_name,
            "information_coefficient": information_coefficient(preds, actual_returns),
            f"top_{top_n}_hit_rate": top_n_hit_rate(preds, actual_returns, top_n),
            f"top_{top_n}_avg_return": top_n_avg_return(preds, actual_returns, top_n),
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values("information_coefficient", ascending=False)
