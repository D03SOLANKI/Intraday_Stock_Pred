"""
Walk-forward validation: train on an expanding (or rolling) window, test on
the next unseen block, then roll forward. This is the primary validation
scheme for the pipeline -- it mimics how the model would actually be
retrained and deployed over time, unlike a single random train/test split
which would badly overstate performance on time-series data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pandas as pd

from config.settings import (
    FINAL_HOLDOUT_DAYS, PURGE_EMBARGO_DAYS, WALK_FORWARD_STEP_DAYS,
    WALK_FORWARD_TEST_DAYS, WALK_FORWARD_TRAIN_MIN_DAYS,
)


@dataclass
class WalkForwardSplit:
    train_dates: pd.DatetimeIndex
    test_dates: pd.DatetimeIndex
    split_index: int


def generate_walk_forward_splits(
    all_dates: pd.DatetimeIndex,
    train_min_days: int = WALK_FORWARD_TRAIN_MIN_DAYS,
    test_days: int = WALK_FORWARD_TEST_DAYS,
    step_days: int = WALK_FORWARD_STEP_DAYS,
    embargo_days: int = PURGE_EMBARGO_DAYS,
    reserve_final_holdout_days: int = FINAL_HOLDOUT_DAYS,
) -> Iterator[WalkForwardSplit]:
    """
    all_dates: sorted unique trading dates across the full dataset.

    The final `reserve_final_holdout_days` are excluded from this generator
    entirely -- they're the untouched final holdout, only ever evaluated
    once after model selection is fully finalized (see
    validation/purged_kfold.py's docstring and pipeline/train_pipeline.py
    for how the holdout is used at the very end).

    Between train and test blocks, `embargo_days` of dates are dropped
    entirely (neither trained nor tested on) to prevent leakage through any
    rolling-window feature whose window straddles the boundary.
    """
    dates = sorted(pd.to_datetime(all_dates).unique())
    usable_dates = dates[:-reserve_final_holdout_days] if reserve_final_holdout_days else dates

    if len(usable_dates) < train_min_days + test_days + embargo_days:
        raise ValueError(
            "Not enough history for even one walk-forward split with the "
            "configured window sizes -- reduce WALK_FORWARD_TRAIN_MIN_DAYS "
            "or gather more data."
        )

    split_index = 0
    train_end_idx = train_min_days
    while True:
        test_start_idx = train_end_idx + embargo_days
        test_end_idx = test_start_idx + test_days
        if test_end_idx > len(usable_dates):
            break

        train_dates = pd.DatetimeIndex(usable_dates[:train_end_idx])
        test_dates = pd.DatetimeIndex(usable_dates[test_start_idx:test_end_idx])

        yield WalkForwardSplit(train_dates=train_dates, test_dates=test_dates, split_index=split_index)

        split_index += 1
        train_end_idx += step_days


def get_final_holdout_dates(
    all_dates: pd.DatetimeIndex, reserve_final_holdout_days: int = FINAL_HOLDOUT_DAYS
) -> pd.DatetimeIndex:
    """The untouched final block -- evaluate on this exactly once, after
    all model selection/hyperparameter tuning is fully locked in."""
    dates = sorted(pd.to_datetime(all_dates).unique())
    return pd.DatetimeIndex(dates[-reserve_final_holdout_days:])
