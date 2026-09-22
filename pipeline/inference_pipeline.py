"""
Daily inference: load the most recent data, compute features as-of today's
close, run each segment's trained ensemble, produce the ranked/explained
output, and log predictions for later scoring.
"""

from __future__ import annotations

import pickle
from datetime import date, timedelta

import pandas as pd

from config.settings import MODEL_STORE_DIR, SEGMENTS
from evaluation.prediction_log import log_predictions
from ranking.rank_and_explain import build_ranked_output, format_output_text


def load_trained_ensembles() -> dict:
    ensembles = {}
    for segment in SEGMENTS:
        path = MODEL_STORE_DIR / f"ensemble_{segment}.pkl"
        if not path.exists():
            print(f"[inference] no trained model for {segment} yet -- run training first")
            continue
        with open(path, "rb") as f:
            ensembles[segment] = pickle.load(f)
    return ensembles


def run_daily_inference(
    current_feature_matrix: pd.DataFrame,
    historical_feature_matrix: pd.DataFrame,
    historical_outcomes: pd.Series,
    calibrators: dict,
    as_of_date: date | None = None,
) -> dict:
    """
    current_feature_matrix: today's (as-of-close) feature rows for every
    symbol across all segments -- must be computed with the exact same
    feature_pipeline.py used in training, on data available strictly up to
    today's close, to predict tomorrow's session.
    """
    as_of_date = as_of_date or date.today()
    ensembles = load_trained_ensembles()
    predictions_by_segment = {}

    for segment, ensemble in ensembles.items():
        seg_features = current_feature_matrix[current_feature_matrix["segment"] == segment]
        if seg_features.empty:
            continue

        group_keys = seg_features["date"].astype(str) + "_" + seg_features["segment"]
        preds = ensemble.predict_rank_averaged(seg_features[ensemble.feature_cols].fillna(0), group_keys)

        lightgbm_model = ensemble.models["lightgbm_regressor"]
        ranked = build_ranked_output(
            segment=segment,
            ensemble_predictions=preds,
            raw_features=seg_features,
            lightgbm_regressor=lightgbm_model,
            calibrator=calibrators[segment],
            historical_feature_matrix=historical_feature_matrix[historical_feature_matrix["segment"] == segment],
            historical_outcomes=historical_outcomes,
            feature_cols=ensemble.feature_cols,
        )
        predictions_by_segment[segment] = ranked

    log_predictions(predictions_by_segment, as_of_date, current_feature_matrix)
    print(format_output_text(predictions_by_segment))
    return predictions_by_segment
