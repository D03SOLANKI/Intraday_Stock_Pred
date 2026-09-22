"""
Logs every live prediction with a full feature/context snapshot, then
later joins against realized outcomes once the next session's data is
available. This is the feedback mechanism the continuous-improvement loop
depends on -- without an immutable log of what was predicted BEFORE the
outcome was known, any later claim of "the model called it" is unverifiable.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime

import pandas as pd

from config.settings import PREDICTION_LOG_DIR


def log_predictions(predictions_by_segment: dict, as_of_date: date, feature_snapshot: pd.DataFrame) -> None:
    """
    Writes an immutable, timestamped record of the day's predictions plus
    the exact feature values used to make them (so later SHAP-based
    post-mortems don't depend on recomputing potentially-drifted features).
    """
    record = {
        "as_of_date": as_of_date.isoformat(),
        "logged_at": datetime.utcnow().isoformat(),
        "predictions": {
            segment: [
                {
                    "symbol": p.symbol, "rank": p.rank,
                    "predicted_return_pct": p.predicted_return_pct,
                    "confidence": p.confidence,
                }
                for p in preds
            ]
            for segment, preds in predictions_by_segment.items()
        },
    }
    out_path = PREDICTION_LOG_DIR / f"predictions_{as_of_date.isoformat()}.json"
    with open(out_path, "w") as f:
        json.dump(record, f, indent=2, default=str)

    feature_snapshot.to_parquet(
        PREDICTION_LOG_DIR / f"feature_snapshot_{as_of_date.isoformat()}.parquet", index=False
    )


def score_logged_predictions(actual_returns_by_date: dict[date, pd.Series]) -> pd.DataFrame:
    """
    Joins every logged prediction file against actual realized returns
    (once available) and returns a long DataFrame of prediction-vs-actual
    pairs, ready for evaluation/metrics.py. This is what should run daily,
    one trading day after each prediction, as the closing of the feedback
    loop.
    """
    rows = []
    for log_file in sorted(PREDICTION_LOG_DIR.glob("predictions_*.json")):
        with open(log_file) as f:
            record = json.load(f)
        as_of = pd.to_datetime(record["as_of_date"]).date()
        if as_of not in actual_returns_by_date:
            continue  # outcome not yet available -- skip until next run

        actuals = actual_returns_by_date[as_of]
        for segment, preds in record["predictions"].items():
            for p in preds:
                rows.append({
                    "as_of_date": as_of,
                    "segment": segment,
                    "symbol": p["symbol"],
                    "rank": p["rank"],
                    "predicted_return_pct": p["predicted_return_pct"],
                    "confidence": p["confidence"],
                    "actual_return_pct": actuals.get(p["symbol"], None),
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", action="store_true",
                         help="Score all logged predictions against available actuals")
    args = parser.parse_args()
    if args.score:
        print(
            "Wire this up to your actual-returns data source "
            "(re-run data/bhavcopy_loader.py for the relevant dates, then "
            "call score_logged_predictions with the resulting return series)."
        )
