"""Common interface every model family implements, so the ensemble and
ranking/evaluation code can treat them interchangeably."""

from __future__ import annotations

import abc

import numpy as np
import pandas as pd


class BasePredictor(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "BasePredictor":
        raise NotImplementedError

    @abc.abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Return predicted forward return (regression) for each row."""
        raise NotImplementedError

    def predict_proba_top_gainer(self, X: pd.DataFrame) -> np.ndarray | None:
        """Optional: probability of being a top-decile gainer. Models that
        don't support this (e.g., pure regressors) return None; the
        ensemble/ranking layer falls back to using predicted return rank
        as a proxy in that case."""
        return None

    def feature_importances(self, feature_names: list[str]) -> pd.Series | None:
        """Optional: global feature importances, if the model exposes them."""
        return None
