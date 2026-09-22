"""
Purged K-Fold cross-validation with embargo, following the methodology in
Marcos Lopez de Prado's "Advances in Financial Machine Learning."

Why this exists in addition to walk_forward.py: walk-forward is the primary
validation scheme for reporting realistic performance, but purged K-fold is
useful during hyperparameter search (it uses data more efficiently than
strict walk-forward while still guarding against the specific leakage mode
that matters here -- overlapping rolling-window features between
neighboring train/test samples).

THE LEAKAGE MODE THIS GUARDS AGAINST: a feature like `ret_20d` on date T
overlaps in its underlying raw data with `ret_20d` on date T+1, T+2, ... up
to T+19. If date T ends up in the test fold and date T+3 ends up in the
training fold, the model can partially "see" test-period information
through that overlap. Purging removes training samples whose feature or
label windows overlap with the test fold; embargo adds a further buffer
after the test fold before training resumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import pandas as pd

from config.settings import LABEL_HORIZON_DAYS, PURGE_EMBARGO_DAYS


@dataclass
class PurgedFold:
    train_idx: np.ndarray
    test_idx: np.ndarray
    fold_index: int


def purged_kfold_split(
    dates: pd.Series,
    n_splits: int = 5,
    label_horizon: int = LABEL_HORIZON_DAYS,
    max_feature_window: int = 252,  # widest rolling window used anywhere
                                     # in features/ (52-week features) --
                                     # purge conservatively against this
    embargo_days: int = PURGE_EMBARGO_DAYS,
) -> Iterator[PurgedFold]:
    """
    dates: the `date` column of the training table, same order/index as
    the feature matrix rows being split.

    Splits the UNIQUE sorted dates into n_splits contiguous test blocks
    (not random samples -- random shuffling of time-series data is itself
    a leakage bug), then purges any training row whose date falls within
    [test_start - max_feature_window, test_end + label_horizon] and applies
    an additional embargo_days buffer after the test block.
    """
    unique_dates = np.array(sorted(dates.unique()))
    n = len(unique_dates)
    fold_bounds = np.array_split(np.arange(n), n_splits)

    for fold_index, test_positions in enumerate(fold_bounds):
        test_dates = unique_dates[test_positions]
        test_start, test_end = test_dates.min(), test_dates.max()

        purge_start = pd.Timestamp(test_start) - pd.Timedelta(days=max_feature_window * 1.5)
        embargo_end = pd.Timestamp(test_end) + pd.Timedelta(days=embargo_days + label_horizon)

        test_mask = dates.isin(test_dates)
        purge_mask = (dates >= purge_start) & (dates <= embargo_end)

        train_idx = dates[~purge_mask].index.to_numpy()
        test_idx = dates[test_mask].index.to_numpy()

        yield PurgedFold(train_idx=train_idx, test_idx=test_idx, fold_index=fold_index)
