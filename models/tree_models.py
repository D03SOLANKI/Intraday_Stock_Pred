"""
Gradient-boosted tree models (primary workhorse for tabular financial
features) and a RandomForest as a robustness check against GBM overfitting.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from config.settings import RANDOM_STATE
from models.base import BasePredictor


class LightGBMRegressor(BasePredictor):
    name = "lightgbm_regressor"

    def __init__(self, **lgb_params):
        default_params = dict(
            n_estimators=400,
            learning_rate=0.03,
            num_leaves=31,
            max_depth=-1,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=0.1,
            random_state=RANDOM_STATE,
        )
        default_params.update(lgb_params)
        self.model = lgb.LGBMRegressor(**default_params)
        self._feature_names: list[str] | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LightGBMRegressor":
        self._feature_names = list(X.columns)
        self.model.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)

    def feature_importances(self, feature_names: list[str]) -> pd.Series:
        importances = self.model.feature_importances_
        return pd.Series(importances, index=feature_names).sort_values(ascending=False)


class LightGBMTopGainerClassifier(BasePredictor):
    """Classifies whether a stock will be in the top decile of forward
    returns cross-sectionally -- gives a genuine calibratable probability,
    complementing the regressor's point-estimate return."""
    name = "lightgbm_classifier"

    def __init__(self, **lgb_params):
        default_params = dict(
            n_estimators=400,
            learning_rate=0.03,
            num_leaves=31,
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=0.1,
            random_state=RANDOM_STATE,
            is_unbalance=True,  # top-decile label is naturally ~10% positive
        )
        default_params.update(lgb_params)
        self.model = lgb.LGBMClassifier(**default_params)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "LightGBMTopGainerClassifier":
        self.model.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        # for interface consistency, "predict" returns the positive-class
        # probability, usable directly as a ranking score
        return self.model.predict_proba(X)[:, 1]

    def predict_proba_top_gainer(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X)[:, 1]

    def feature_importances(self, feature_names: list[str]) -> pd.Series:
        importances = self.model.feature_importances_
        return pd.Series(importances, index=feature_names).sort_values(ascending=False)


class RandomForestBaseline(BasePredictor):
    """Robustness check: if LightGBM's out-of-sample performance is
    dramatically better than this simpler, harder-to-overfit baseline,
    that's a signal to scrutinize the GBM for overfitting rather than
    celebrate."""
    name = "random_forest"

    def __init__(self, **rf_params):
        default_params = dict(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=20,
            n_jobs=-1,
            random_state=RANDOM_STATE,
        )
        default_params.update(rf_params)
        self.model = RandomForestRegressor(**default_params)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RandomForestBaseline":
        self.model.fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)

    def feature_importances(self, feature_names: list[str]) -> pd.Series:
        return pd.Series(self.model.feature_importances_, index=feature_names).sort_values(ascending=False)
