"""
End-to-end training orchestrator: data -> features -> labels -> walk-
forward validated training -> final holdout evaluation -> persisted models.

Run stages independently since the full pipeline over years of NSE history
is not a quick single call:
    python -m pipeline.train_pipeline --stage data
    python -m pipeline.train_pipeline --stage train
"""

from __future__ import annotations

import argparse
import pickle
from datetime import date

import pandas as pd

from config.settings import MODEL_STORE_DIR, SEGMENTS
from data.bhavcopy_loader import BhavcopyLoader
from data.corporate_actions import adjust_via_yfinance_crosscheck
from data.universe import approximate_by_market_cap_rank, load_archived_constituent_snapshots
from data.yfinance_loader import YFinanceLoader
from evaluation.metrics import evaluate_split
from features.feature_pipeline import build_universe_features
from labels import assemble_training_table
from models.ensemble import train_ensemble
from validation.walk_forward import generate_walk_forward_splits, get_final_holdout_dates


def stage_data(symbols: list[str], start: date, end: date) -> pd.DataFrame:
    """Pull and cache raw OHLCV from both free sources, cross-check-adjust
    for corporate actions. Returns the cleaned universe DataFrame."""
    bhav = BhavcopyLoader()
    yf_loader = YFinanceLoader()

    bhav_df = bhav.fetch_ohlcv(symbols, start, end)
    yf_df = yf_loader.fetch_ohlcv(symbols, start, end)

    adjusted = adjust_via_yfinance_crosscheck(bhav_df, yf_df)
    return adjusted


def stage_universe_tagging(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach segment (large/mid/small cap) labels. Prefers real point-in-time
    constituent snapshots if available; falls back to the market-cap-rank
    approximation with a loud warning -- see data/universe.py docstring for
    why this distinction matters (survivorship bias).
    """
    snapshots = load_archived_constituent_snapshots()
    if snapshots.empty:
        print(
            "[WARNING] No archived index-constituent snapshots found in "
            "data_store/universe/. Falling back to market-cap-rank "
            "approximation, which needs a shares-outstanding source you "
            "must supply separately. Segment labels will be an "
            "approximation until real snapshots are added -- see "
            "data/universe.py."
        )
        raise NotImplementedError(
            "Supply a shares_outstanding DataFrame and call "
            "approximate_by_market_cap_rank() per date, or add constituent "
            "snapshot CSVs to data_store/universe/."
        )

    # real snapshot path: join each row's date against the point-in-time table
    from data.universe import get_segment_as_of
    raw_df = raw_df.copy()
    raw_df["segment"] = raw_df.apply(
        lambda r: get_segment_as_of(snapshots, r["symbol"], r["date"]), axis=1
    )
    return raw_df.dropna(subset=["segment"])


def stage_train(training_table: pd.DataFrame, feature_cols: list[str]) -> dict:
    """
    Runs walk-forward validation per segment, training a fresh ensemble on
    each split's train window and evaluating on its test window, then
    trains a final model per segment on ALL data up to the final holdout
    boundary (the final holdout itself is evaluated once, separately, via
    stage_final_holdout_eval below).
    """
    results = {}
    for segment in SEGMENTS:
        seg_df = training_table[training_table["segment"] == segment].dropna(subset=["date"])
        if seg_df.empty:
            print(f"[train] no data for segment={segment}, skipping")
            continue

        seg_df = seg_df.sort_values("date")
        split_reports = []

        for split in generate_walk_forward_splits(pd.to_datetime(seg_df["date"])):
            train_mask = pd.to_datetime(seg_df["date"]).isin(split.train_dates)
            test_mask = pd.to_datetime(seg_df["date"]).isin(split.test_dates)

            train_split = seg_df[train_mask].dropna(subset=["label_fwd_return"])
            test_split = seg_df[test_mask].dropna(subset=["label_fwd_return"])
            if train_split.empty or test_split.empty:
                continue

            ensemble = train_ensemble(train_split, feature_cols)
            preds_by_model = {
                name: pd.Series(model.predict(test_split[feature_cols].fillna(0)), index=test_split.index)
                for name, model in ensemble.models.items()
            }
            report = evaluate_split(preds_by_model, test_split["label_fwd_return"])
            report["split_index"] = split.split_index
            split_reports.append(report)
            print(f"[train] segment={segment} split={split.split_index} done")

        results[segment] = pd.concat(split_reports, ignore_index=True) if split_reports else pd.DataFrame()

    return results


def stage_final_holdout_eval(training_table: pd.DataFrame, feature_cols: list[str]) -> dict:
    """
    Trains ONE final model per segment on everything except the final
    holdout block, evaluates ONCE on that untouched holdout, and persists
    the trained ensemble. This should only be run after all model
    selection/hyperparameter decisions from stage_train are fully locked in
    -- re-running this repeatedly and adjusting based on holdout results
    defeats its purpose.
    """
    final_results = {}
    for segment in SEGMENTS:
        seg_df = training_table[training_table["segment"] == segment].dropna(subset=["date"])
        if seg_df.empty:
            continue

        holdout_dates = get_final_holdout_dates(pd.to_datetime(seg_df["date"]))
        train_df = seg_df[~pd.to_datetime(seg_df["date"]).isin(holdout_dates)].dropna(subset=["label_fwd_return"])
        holdout_df = seg_df[pd.to_datetime(seg_df["date"]).isin(holdout_dates)].dropna(subset=["label_fwd_return"])

        if train_df.empty or holdout_df.empty:
            continue

        ensemble = train_ensemble(train_df, feature_cols)
        preds_by_model = {
            name: pd.Series(model.predict(holdout_df[feature_cols].fillna(0)), index=holdout_df.index)
            for name, model in ensemble.models.items()
        }
        report = evaluate_split(preds_by_model, holdout_df["label_fwd_return"])
        final_results[segment] = report

        with open(MODEL_STORE_DIR / f"ensemble_{segment}.pkl", "wb") as f:
            pickle.dump(ensemble, f)

    return final_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["data", "features", "train", "final_holdout"], required=True)
    args = parser.parse_args()

    print(
        f"Stage '{args.stage}' selected. This scaffold defines the "
        "functions; wire in your symbol list / date range in a driver "
        "script or notebook, since a live NSE universe pull is a "
        "long-running, rate-limited operation not meant to run inline "
        "here."
    )
