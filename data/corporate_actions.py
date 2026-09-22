"""
Corporate action adjustment (splits, bonuses, dividends).

Why this matters: an unadjusted 1:2 stock split shows up as a ~50% single-day
"return," which would poison every momentum/volatility feature and, worse,
could leak into the label as a fake "top gainer/loser" day. This module
must run BEFORE feature engineering.

Free-tier reality: NSE bhavcopy does not include a corporate-actions feed.
Two supported strategies:
  1. `AdjustedCloseCrossCheck`: use yfinance's auto-adjusted close series to
     detect and back-adjust bhavcopy prices (works reasonably well, not
     perfect for all bonus/rights-issue edge cases).
  2. `ExplicitActionsTable`: if you obtain a corporate-actions CSV (NSE
     publishes one at nseindia.com/companies-listing/corporate-filings-actions,
     free but requires separate scraping/registration), feed it here directly
     for exact adjustment.

Both paths produce the same output contract: an `adj_close` column and an
adjustment-factor series applied consistently to open/high/low/close/volume.
"""

from __future__ import annotations

import pandas as pd


def adjust_via_yfinance_crosscheck(
    bhavcopy_df: pd.DataFrame, yfinance_df: pd.DataFrame
) -> pd.DataFrame:
    """
    For each symbol, compute the implied adjustment factor per date by
    comparing bhavcopy's unadjusted close to yfinance's auto-adjusted close,
    then propagate that factor backward through history and apply it to
    open/high/low/close (volume is inversely adjusted).

    This is a heuristic cross-check, not a guarantee -- always spot-check a
    handful of known-split/bonus stocks after running this.
    """
    merged = bhavcopy_df.merge(
        yfinance_df[["symbol", "date", "close"]].rename(
            columns={"close": "yf_adj_close"}
        ),
        on=["symbol", "date"],
        how="left",
    )

    out_frames = []
    for symbol, grp in merged.groupby("symbol"):
        grp = grp.sort_values("date").copy()
        # ratio between the two sources; a jump in this ratio flags an
        # unadjusted corporate action in the bhavcopy series
        grp["ratio"] = grp["yf_adj_close"] / grp["close"]
        grp["ratio"] = grp["ratio"].bfill().ffill()
        # normalise so the most recent ratio == 1.0 (i.e., adjust history
        # backward relative to the present, standard practice)
        if grp["ratio"].notna().any():
            latest_ratio = grp["ratio"].iloc[-1]
            grp["adj_factor"] = grp["ratio"] / latest_ratio
        else:
            grp["adj_factor"] = 1.0

        for col in ["open", "high", "low", "close"]:
            grp[f"adj_{col}"] = grp[col] * grp["adj_factor"]
        grp["adj_volume"] = grp["volume"] / grp["adj_factor"].replace(0, pd.NA)

        out_frames.append(grp)

    return pd.concat(out_frames, ignore_index=True).drop(columns=["ratio"])


def apply_explicit_actions_table(
    price_df: pd.DataFrame, actions_df: pd.DataFrame
) -> pd.DataFrame:
    """
    actions_df expected columns: ['symbol', 'ex_date', 'action_type',
    'ratio_or_amount'] (action_type in {'split', 'bonus', 'dividend'}).
    Placeholder for when you wire up an explicit corporate-actions feed --
    implement precise back-adjustment per action_type here.
    """
    raise NotImplementedError(
        "Plug in an explicit NSE corporate-actions feed here for exact "
        "adjustment; until then, use adjust_via_yfinance_crosscheck()."
    )
