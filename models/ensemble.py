"""
Ensemble layer: trains multiple model families, then combines their
outputs via rank-averaging (more robust than averaging raw predictions,
since different models' predicted-return scales aren't directly
comparable, but their within-day RANKS are).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from models.base import BasePredictor
from models.linear_models import NaiveMeanReversionBaseline, NaiveMomentumBaseline, RidgeBaseline
from models.tree_models import LightGBMRegressor, LightGBMTopGainerClassifier, RandomForestBaseline


@dataclass
class TrainedEnsemble:
    models: dict[str, BasePredictor] = field(default_factory=dict)
    feature_cols: list[str] = field(default_factory=list)

    def predict_rank_averaged(self, X: pd.DataFrame, group_keys: pd.Series) -> pd.DataFrame:
        """
        group_keys: a Series aligned to X's index identifying which
        (date, segment) group each row belongs to -- ranking is only
        meaningful within a group, never across different days/segments.

        Returns a DataFrame with each model's raw prediction, each
        model's within-group percentile rank, and a final `ensemble_rank`
        averaged across models (then itself converted to a percentile).
        """
        result = pd.DataFrame(index=X.index)
        result["group_key"] = group_keys.values

        rank_cols = []
        for model_name, model in self.models.items():
            preds = model.predict(X[self.feature_cols])
            result[f"pred_{model_name}"] = preds
            result[f"rank_{model_name}"] = (
                result.groupby("group_key")[f"pred_{model_name}"].rank(pct=True)
            )
            rank_cols.append(f"rank_{model_name}")

        result["ensemble_rank_raw"] = result[rank_cols].mean(axis=1)
        result["ensemble_rank_pct"] = result.groupby("group_key")["ensemble_rank_raw"].rank(pct=True)
        return result


def build_default_model_suite() -> dict[str, BasePredictor]:
    """
    The standard suite trained per segment: a GBM regressor (primary),
    a GBM classifier (top-gainer probability), a RandomForest (overfitting
    check), a regularized linear baseline (interpretability check), and
    two naive heuristic baselines (the bar the ML models must clear).
    Learning-to-rank and the sequence model are trained separately (see
    models/ranking_model.py, models/sequence_model.py) since they need
    different input shapes (grouped rows / 3D sequences respectively).
    """
    return {
        "lightgbm_regressor": LightGBMRegressor(),
        "lightgbm_classifier": LightGBMTopGainerClassifier(),
        "random_forest": RandomForestBaseline(),
        "ridge": RidgeBaseline(),
        "naive_momentum": NaiveMomentumBaseline(),
        "naive_mean_reversion": NaiveMeanReversionBaseline(),
    }


def train_ensemble(
    train_df: pd.DataFrame, feature_cols: list[str],
    regression_target: str = "label_fwd_return",
    classification_target: str = "label_is_top_gainer",
) -> TrainedEnsemble:
    X = train_df[feature_cols].fillna(0)
    y_reg = train_df[regression_target]
    y_clf = train_df[classification_target]

    models = build_default_model_suite()
    for name, model in models.items():
        target = y_clf if name == "lightgbm_classifier" else y_reg
        model.fit(X, target)

    return TrainedEnsemble(models=models, feature_cols=feature_cols)
