"""
Monitors live (post-deployment) performance against the backtested
expectation and flags when retraining is warranted. Thresholds here are
statistical placeholders (documented as such) -- tune them once you have
enough live history to know what "normal" variance in these metrics looks
like for this specific pipeline; don't treat the defaults as validated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class DriftReport:
    ic_backtest_mean: float
    ic_live_rolling_mean: float
    ic_degradation: float
    should_retrain: bool
    reason: str


def check_for_drift(
    backtest_ic_history: pd.Series,
    live_ic_history: pd.Series,
    rolling_window: int = 20,
    degradation_std_threshold: float = 1.5,
) -> DriftReport:
    """
    Compares a rolling window of live information-coefficient values
    against the backtested distribution. If live IC has dropped more than
    `degradation_std_threshold` standard deviations below the backtest
    mean, flags a retrain. `degradation_std_threshold` is a placeholder --
    calibrate it against your own live variance once you have several
    months of live IC history; 1.5 std is a starting point, not a
    validated cutoff.
    """
    backtest_mean = backtest_ic_history.mean()
    backtest_std = backtest_ic_history.std()
    live_recent = live_ic_history.tail(rolling_window)
    live_mean = live_recent.mean()

    degradation = (backtest_mean - live_mean) / backtest_std if backtest_std > 0 else np.nan
    should_retrain = bool(degradation is not np.nan and degradation > degradation_std_threshold)

    reason = (
        f"Live IC ({live_mean:.4f}) is {degradation:.2f} std below backtest mean "
        f"({backtest_mean:.4f}) over the last {rolling_window} sessions."
        if should_retrain else
        "Live performance within expected range of backtest distribution."
    )

    return DriftReport(
        ic_backtest_mean=float(backtest_mean),
        ic_live_rolling_mean=float(live_mean),
        ic_degradation=float(degradation) if degradation is not np.nan else np.nan,
        should_retrain=should_retrain,
        reason=reason,
    )
