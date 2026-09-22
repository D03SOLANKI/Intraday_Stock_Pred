"""
Target/label construction. This is the ONLY file in the codebase permitted
to use T+1 (future) data -- kept isolated on purpose so leakage risk is
auditable in one place. Labels are computed as their own DataFrame and only
joined onto the feature matrix at the very last step of training-data
assembly (see pipeline/train_pipeline.py), never during feature
engineering or during inference-time feature computation.
"""

from __future__ import annotations

import pandas as pd

from config.settings import LABEL_HORIZON_DAYS, LABEL_PRICE_FIELD, TOP_DECILE_THRESHOLD


def build_regression_labels(
    raw_universe_df: pd.DataFrame, horizon: int = LABEL_HORIZON_DAYS,
    price_field: str = LABEL_PRICE_FIELD,
) -> pd.DataFrame:
    """
    Returns ['symbol', 'date', 'label_fwd_return'] where `date` is the
    LAST DAY the feature row is "as of" (i.e., the prediction is made using
    data through `date`, and label_fwd_return is the return realized over
    the following `horizon` session(s), close-to-close by default).

    Example: date=2026-09-17, label_fwd_return = return from 17 Sep close
    to 18 Sep close. A model trained on features "as of 17 Sep" predicting
    this label is predicting 18 Sep's session -- exactly the next-session
    task requested.
    """
    frames = []
    for symbol, grp in raw_universe_df.sort_values("date").groupby("symbol"):
        grp = grp.copy()
        fwd_price = grp[price_field].shift(-horizon)
        grp["label_fwd_return"] = (fwd_price - grp[price_field]) / grp[price_field]
        frames.append(grp[["symbol", "date", "label_fwd_return"]])
    return pd.concat(frames, ignore_index=True)


def build_topgainer_classification_labels(
    regression_labels: pd.DataFrame, threshold_percentile: float = TOP_DECILE_THRESHOLD
) -> pd.DataFrame:
    """
    Converts forward returns into a same-day cross-sectional percentile
    rank, then flags the top decile (or whatever threshold_percentile is
    set to) as label_is_top_gainer = 1. This is deliberately a PERCENTILE
    within each day's cross-section, not a fixed return cutoff (e.g., not
    "return > 5%") -- so the definition of "top gainer" adapts to whatever
    the day's overall volatility regime was, rather than hardcoding what
    counts as a big move.
    """
    df = regression_labels.copy()
    df["label_fwd_return_xs_rank"] = df.groupby("date")["label_fwd_return"].rank(pct=True)
    df["label_is_top_gainer"] = (df["label_fwd_return_xs_rank"] >= threshold_percentile).astype(int)
    return df


def assemble_training_table(
    feature_matrix: pd.DataFrame, raw_universe_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Final join of features (as of date T) with labels (forward return
    realized after T). This is the single point where features and future
    outcomes meet -- after this join, the table must never be used to
    derive NEW features (that would be equivalent to leaking the label back
    into feature engineering for other rows).
    """
    reg_labels = build_regression_labels(raw_universe_df)
    clf_labels = build_topgainer_classification_labels(reg_labels)
    labels = reg_labels.merge(
        clf_labels[["symbol", "date", "label_fwd_return_xs_rank", "label_is_top_gainer"]],
        on=["symbol", "date"], how="left",
    )
    training_table = feature_matrix.merge(labels, on=["symbol", "date"], how="left")
    # Rows with no forward label (the most recent `horizon` days, where
    # tomorrow's price doesn't exist yet) are exactly the rows used for
    # live inference, not training -- drop them from the TRAINING split
    # explicitly rather than silently.
    return training_table
