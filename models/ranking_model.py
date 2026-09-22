"""
Learning-to-rank model (LightGBM's LambdaMART ranker). Arguably the most
appropriate model family for this task: rather than optimizing pointwise
prediction error (MSE on return, or log-loss on top-gainer classification),
it directly optimizes the QUALITY OF THE RANKING within each day's
cross-section -- which is exactly what "rank stocks by predicted next-
session gain" needs.

LightGBM's ranker requires a `group` array telling it how many consecutive
rows belong to the same "query" (here: the same trading day + segment,
since ranking only makes sense within a peer group on the same day).
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from config.settings import RANDOM_STATE
from models.base import BasePredictor


class LambdaMARTRanker(BasePredictor):
    name = "lambdamart_ranker"

    def __init__(self, **lgb_params):
        default_params = dict(
            n_estimators=400,
            learning_rate=0.03,
            num_leaves=31,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=RANDOM_STATE,
            objective="lambdarank",
            metric="ndcg",
        )
        default_params.update(lgb_params)
        self.model = lgb.LGBMRanker(**default_params)

    def fit(self, X: pd.DataFrame, y: pd.Series, groups: np.ndarray | None = None,
            relevance_bins: int = 10) -> "LambdaMARTRanker":
        """
        groups: array of group sizes matching X's row order (e.g., number
        of stocks in each (date, segment) group, consecutive). If not
        provided, caller must have pre-sorted X/y by (date, segment) and
        pass groups computed via `groupby(['date','segment']).size()`.

        y (continuous forward return) is discretized into relevance bins
        (0..relevance_bins-1) via cross-sectional rank within each group,
        since LambdaMART expects ordinal relevance labels, not continuous
        targets.
        """
        if groups is None:
            raise ValueError("groups is required -- see models/ranking_model.py docstring")
        relevance = self._to_relevance_bins(y, groups, relevance_bins)
        self.model.fit(X, relevance, group=groups)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        # raw ranking scores -- higher = predicted higher rank. Not a
        # calibrated return estimate; use alongside the regressor for that.
        return self.model.predict(X)

    def feature_importances(self, feature_names: list[str]) -> pd.Series:
        return pd.Series(self.model.feature_importances_, index=feature_names).sort_values(ascending=False)

    @staticmethod
    def _to_relevance_bins(y: pd.Series, groups: np.ndarray, n_bins: int) -> np.ndarray:
        relevance = np.zeros(len(y), dtype=int)
        pos = 0
        y_arr = y.to_numpy()
        for g in groups:
            chunk = y_arr[pos:pos + g]
            ranks = pd.Series(chunk).rank(pct=True)
            relevance[pos:pos + g] = np.minimum((ranks * n_bins).astype(int), n_bins - 1)
            pos += g
        return relevance
