"""
Regularized linear model as an interpretable baseline, plus naive
heuristic baselines. The naive baselines matter more than they might look
-- if the ML models can't beat these out-of-sample, the ML models aren't
adding real value yet, regardless of how sophisticated they seem.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from config.settings import RANDOM_STATE
from models.base import BasePredictor


class RidgeBaseline(BasePredictor):
    name = "ridge_regression"

    def __init__(self, alpha: float = 1.0):
        self.model = Ridge(alpha=alpha, random_state=RANDOM_STATE)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RidgeBaseline":
        self.model.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)

    def feature_importances(self, feature_names: list[str]) -> pd.Series:
        return pd.Series(np.abs(self.model.coef_), index=feature_names).sort_values(ascending=False)


class NaiveMomentumBaseline(BasePredictor):
    """
    'Predicts' tomorrow's return using recent momentum (e.g., yesterday's
    return, or a short trailing average return). This needs no training in
    the ML sense -- fit() just remembers which column to read from `predict`'s
    X directly. It exists purely so every reported result can state "the
    ML model beat/did not beat this trivial heuristic out-of-sample."
    """
    name = "naive_momentum_baseline"

    def __init__(self, momentum_col: str = "ret_5d"):
        self.momentum_col = momentum_col

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "NaiveMomentumBaseline":
        return self  # stateless

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.momentum_col not in X.columns:
            raise KeyError(f"{self.momentum_col} not in feature matrix")
        return X[self.momentum_col].fillna(0).to_numpy()


class NaiveMeanReversionBaseline(BasePredictor):
    """Alternative naive baseline: predicts the negative of recent return
    (mean-reversion heuristic). Which naive baseline wins historically is
    itself informative about the prevailing regime (momentum vs
    mean-reverting)."""
    name = "naive_mean_reversion_baseline"

    def __init__(self, momentum_col: str = "ret_1d"):
        self.momentum_col = momentum_col

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "NaiveMeanReversionBaseline":
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return -X[self.momentum_col].fillna(0).to_numpy()
