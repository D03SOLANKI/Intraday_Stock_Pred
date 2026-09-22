"""
Turns raw ensemble predictions into the final ranked, explained output per
segment: rank, predicted return, calibrated confidence, key
signals/features (via SHAP), volatility/risk context, and a nearest-
neighbor lookup of historically similar setups.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shap
from sklearn.isotonic import IsotonicRegression
from sklearn.neighbors import NearestNeighbors

from config.settings import N_ENSEMBLE_TOP_FEATURES_TO_EXPLAIN, TOP_N_PER_SEGMENT


@dataclass
class StockPrediction:
    symbol: str
    segment: str
    rank: int
    predicted_return_pct: float
    confidence: float  # calibrated probability of being a genuine top gainer
    predicted_volatility_pct: float
    top_signals: list[tuple[str, float]]  # (feature_name, shap_contribution)
    similar_setups_avg_return_pct: float
    similar_setups_hit_rate: float
    n_similar_setups: int


class ConfidenceCalibrator:
    """
    Calibrates the classifier's raw probability output against actually
    observed hit rates using isotonic regression fit on validation-fold
    predictions (never on training data -- calibration on train data would
    itself be a subtle leakage/overfitting mode, since the model is always
    overconfident on data it was fit to).
    """

    def __init__(self):
        self.calibrator = IsotonicRegression(out_of_bounds="clip")
        self._fitted = False

    def fit(self, val_raw_probs: np.ndarray, val_actual_outcomes: np.ndarray) -> "ConfidenceCalibrator":
        self.calibrator.fit(val_raw_probs, val_actual_outcomes)
        self._fitted = True
        return self

    def transform(self, raw_probs: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Calibrator must be fit on held-out validation predictions first")
        return self.calibrator.predict(raw_probs)


def explain_with_shap(
    lightgbm_model, X_row: pd.DataFrame, top_k: int = N_ENSEMBLE_TOP_FEATURES_TO_EXPLAIN
) -> list[tuple[str, float]]:
    """
    Returns the top_k features driving this specific prediction, by
    absolute SHAP value, for one row (one stock, one day). Uses
    TreeExplainer since the primary model is LightGBM.
    """
    explainer = shap.TreeExplainer(lightgbm_model.model)
    shap_values = explainer.shap_values(X_row)
    if isinstance(shap_values, list):  # classifier returns per-class list
        shap_values = shap_values[1]
    contributions = pd.Series(shap_values[0], index=X_row.columns)
    top = contributions.reindex(contributions.abs().sort_values(ascending=False).index[:top_k])
    return list(top.items())


def find_similar_historical_setups(
    current_feature_vector: pd.Series,
    historical_feature_matrix: pd.DataFrame,
    historical_outcomes: pd.Series,
    feature_cols: list[str],
    n_neighbors: int = 30,
) -> dict:
    """
    Nearest-neighbor lookup (on standardized feature space) to answer
    "how did setups that looked like this actually perform historically?"
    -- grounds the prediction in an interpretable base rate rather than
    just trusting the model's point estimate.
    """
    from sklearn.preprocessing import StandardScaler

    hist_X = historical_feature_matrix[feature_cols].fillna(0)
    scaler = StandardScaler().fit(hist_X)
    hist_X_scaled = scaler.transform(hist_X)
    current_scaled = scaler.transform(current_feature_vector[feature_cols].fillna(0).to_frame().T)

    nn = NearestNeighbors(n_neighbors=min(n_neighbors, len(hist_X_scaled)))
    nn.fit(hist_X_scaled)
    _, indices = nn.kneighbors(current_scaled)

    neighbor_outcomes = historical_outcomes.iloc[indices[0]]
    return {
        "avg_return_pct": float(neighbor_outcomes.mean() * 100),
        "hit_rate": float((neighbor_outcomes > 0).mean()),
        "n_similar_setups": int(len(neighbor_outcomes)),
    }


def build_ranked_output(
    segment: str,
    ensemble_predictions: pd.DataFrame,  # from TrainedEnsemble.predict_rank_averaged
    raw_features: pd.DataFrame,
    lightgbm_regressor,
    calibrator: ConfidenceCalibrator,
    historical_feature_matrix: pd.DataFrame,
    historical_outcomes: pd.Series,
    feature_cols: list[str],
    top_n: int = TOP_N_PER_SEGMENT,
) -> list[StockPrediction]:
    """Assembles the final, explained, ranked list for one segment."""
    ranked = ensemble_predictions.sort_values("ensemble_rank_pct", ascending=False).head(top_n)

    results = []
    for i, (idx, row) in enumerate(ranked.iterrows(), start=1):
        symbol = raw_features.loc[idx, "symbol"]
        X_row = raw_features.loc[[idx], feature_cols].fillna(0)

        predicted_return = row.get("pred_lightgbm_regressor", np.nan)
        raw_prob = row.get("pred_lightgbm_classifier", np.nan)
        confidence = float(calibrator.transform(np.array([raw_prob]))[0]) if not np.isnan(raw_prob) else np.nan

        predicted_vol = raw_features.loc[idx].get("realized_vol_20d", np.nan)

        top_signals = explain_with_shap(lightgbm_regressor, X_row)

        similar = find_similar_historical_setups(
            raw_features.loc[idx], historical_feature_matrix, historical_outcomes, feature_cols
        )

        results.append(StockPrediction(
            symbol=symbol,
            segment=segment,
            rank=i,
            predicted_return_pct=float(predicted_return * 100),
            confidence=confidence,
            predicted_volatility_pct=float(predicted_vol * 100) if not np.isnan(predicted_vol) else np.nan,
            top_signals=top_signals,
            similar_setups_avg_return_pct=similar["avg_return_pct"],
            similar_setups_hit_rate=similar["hit_rate"],
            n_similar_setups=similar["n_similar_setups"],
        ))

    return results


def format_output_text(predictions_by_segment: dict[str, list[StockPrediction]]) -> str:
    """Renders the final human-readable output in the format requested."""
    segment_titles = {"large_cap": "Large Cap", "mid_cap": "Mid Cap", "small_cap": "Small Cap"}
    lines = []
    for segment, preds in predictions_by_segment.items():
        lines.append(f"\n{segment_titles.get(segment, segment)}\n")
        for p in preds:
            lines.append(f"Rank {p.rank}: {p.symbol} — predicted return: {p.predicted_return_pct:+.2f}%")
            lines.append(f"    Confidence (calibrated): {p.confidence:.1%}" if not np.isnan(p.confidence) else "    Confidence: n/a")
            lines.append(f"    Predicted 20d volatility: {p.predicted_volatility_pct:.1f}%")
            signals = ", ".join(f"{name} ({val:+.3f})" for name, val in p.top_signals)
            lines.append(f"    Key signals: {signals}")
            lines.append(
                f"    Similar historical setups (n={p.n_similar_setups}): "
                f"avg return {p.similar_setups_avg_return_pct:+.2f}%, "
                f"hit rate {p.similar_setups_hit_rate:.1%}"
            )
    return "\n".join(lines)
