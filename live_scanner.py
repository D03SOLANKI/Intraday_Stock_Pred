"""
Production 09:30 AM Point-in-Time Live Scanner
OPTION 3: MACHINE LEARNING TOP-3 NEXT-DAY MID-CAP GAINER ENGINE (DEFAULT)

Engines:
    --engine ml_top3    (Default) Option 3 ML Top-3 Next-Day Gainer Strategy
                        LambdaMART Ranker + TGPI Ensemble (Captures 5% to 20% runners)
    --engine pit        Option 1 Improved PIT Fixed Sizing Strategy

Run:
    python live_scanner.py                        # latest historical session (Option 3 ML Top 3)
    python live_scanner.py --date 2026-09-18      # specific date
    python live_scanner.py --live                  # force live NSE download
    python live_scanner.py --equity 10000000      # custom active equity
    python live_scanner.py --engine pit           # switch to Option 1
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

IST = timezone(timedelta(hours=5, minutes=30))

from strategy.ml_top3_gainer_strategy import (
    MLTop3GainerStrategy,
    NIFTY100_LARGE_CAP_EXCLUSIONS,
)
from strategy.improved_point_in_time_strategy import ImprovedPointInTimeStrategy

LARGE_CAP_EXCLUSIONS = NIFTY100_LARGE_CAP_EXCLUSIONS


def load_midcap_universe(csv_path: str = "nifty_midcap_150.csv") -> list:
    """
    Loads official Nifty Midcap 150 universe and structurally purges Large-Caps.
    """
    if not os.path.exists(csv_path):
        csv_path = os.path.join(os.path.dirname(__file__), "nifty_midcap_150.csv")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CRITICAL: Universe file '{csv_path}' not found.")

    df = pd.read_csv(csv_path)
    raw_symbols = df["Symbol"].dropna().unique().tolist()

    midcap_symbols = []
    for s in raw_symbols:
        s_clean = s.strip().upper()
        if s_clean not in NIFTY100_LARGE_CAP_EXCLUSIONS:
            midcap_symbols.append(s_clean)

    return midcap_symbols


def run_scanner(
    trading_date: str = None,
    active_equity: float = 10_000_000.0,
    data_path: str = "all_midcap_stock_days_5year.pkl",
    engine: str = "ml_top3",
    force_live: bool = False,
) -> pd.DataFrame:
    now_ist = datetime.now(IST)
    print("=" * 85)
    print(f"POINT-IN-TIME 09:30 AM MID-CAP SCANNER — [{engine.upper()} PRODUCTION ENGINE]")
    print(f"Active Portfolio Equity: Rs. {active_equity:,.2f}")
    print(f"Execution Timestamp:     {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
    print("=" * 85)

    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Data file '{data_path}' not found.")

    if engine == "ml_top3":
        # ── OPTION 3: ML TOP-3 NEXT-DAY GAINER ENGINE ─────────────────────────
        strat = MLTop3GainerStrategy(initial_equity=active_equity)
        raw_df = pd.read_pickle(data_path)
        raw_df['date'] = pd.to_datetime(raw_df['date'])
        raw_df = raw_df.sort_values(['symbol', 'date']).reset_index(drop=True)

        feat_df = strat.compute_features(raw_df)
        all_dates = sorted(feat_df['date'].unique())

        target_date = pd.to_datetime(trading_date) if trading_date else all_dates[-1]
        print(f"Scanning Target Session: {target_date.strftime('%Y-%m-%d')}")

        day_panel = feat_df[feat_df['date'] == target_date]
        if day_panel.empty:
            print("[INFO] No data available for requested date. Zero orders placed.")
            return pd.DataFrame()

        # Generate ML Top-3 Predictions
        top3_cands = strat.predict_top3_candidates(day_panel)
        if top3_cands.empty:
            print("[INFO] Zero candidates met quality criteria. 100% Cash preserved.")
            return pd.DataFrame()

        print(f"\nML Model ranked {len(day_panel)} pure midcaps. Top candidates generated:")

        orders = []
        print("\n" + "─" * 85)
        print("ACTIONABLE 09:30 AM BUY ORDERS — PREDICTED TOP MID-CAP GAINERS")
        print("─" * 85)

        for rank_idx, (_, row) in enumerate(top3_cands.iterrows(), 1):
            sym = row['symbol']
            curr_px = row.get('close', row.get('prev_close', 0))
            entry_price = curr_px * (1.0 + strat.entry_slippage_pct)
            initial_sl = entry_price * (1.0 - strat.initial_sl_pct)
            adv_inr = row.get('adv_20d_cr', 5.0) * 10_000_000.0
            allocated_cap, shares = strat.calculate_position_size(active_equity, adv_inr, entry_price)

            if shares <= 0:
                continue

            rationale = strat.generate_trade_rationale(row, rank_idx=rank_idx)

            orders.append({
                'Rank': f"#{rank_idx}",
                'Symbol': sym,
                'TGPI Score': round(row['tgpi_score'], 3),
                'Top-3 Prob %': round(row['prob_top3'] * 100, 1),
                'Expected Ret %': round(row['pred_return'], 2),
                'Entry Limit (₹)': round(entry_price, 2),
                'Stop Loss (₹)': round(initial_sl, 2),
                'Shares': shares,
                'Capital (₹)': round(allocated_cap, 2),
                'Equity %': round((allocated_cap / active_equity) * 100, 1),
                'Trade Logic': rationale['summary'],
                'Key Drivers': " • ".join(rationale['drivers']),
                'Volume Surge': f"{rationale['vol_surge']:.2f}x",
                'Range Position': f"{rationale['range_pos']:.0f}%",
                'Sector Alpha': f"{rationale['sector_alpha']:+.2f}%",
                'Dist 20-DMA': f"{rationale['dist_sma20']:+.1f}%",
                'RSI': f"{rationale['rsi']:.1f}"
            })

            print(f"  #{rank_idx}: [{sym:<11}] | TGPI Score: {row['tgpi_score']:.3f} | Top-3 Prob: {row['prob_top3']*100:.1f}%")
            print(f"       Entry Limit: Rs. {entry_price:,.2f} | Shares: {shares:,} | Capital: Rs. {allocated_cap:,.2f} ({(allocated_cap/active_equity)*100:.1f}% equity)")
            print(f"       Initial SL (-2.5%): Rs. {initial_sl:,.2f} | Target: Dynamic Trailing Stop (Runners)")
            print(f"       Rationale: {rationale['summary'][:90]}...")

        orders_df = pd.DataFrame(orders)
        orders_df.to_csv("daily_live_scan_orders.csv", index=False)
        print(f"\nOrders saved → daily_live_scan_orders.csv ({len(orders_df)} orders)")

        # Synchronize Paper Trading Portfolio Ledger
        try:
            from order_manager import OrderManager
            om = OrderManager()
            print(f"Paper Trading Ledger synchronized: {len([p for p in om.positions if p['status'] == 'OPEN'])} open positions.")
        except Exception as om_err:
            print(f"Note: Paper Ledger sync: {om_err}")

        return orders_df

    else:
        # ── OPTION 1: IMPROVED PIT FIXED SIZING ENGINE ─────────────────────────
        strat = ImprovedPointInTimeStrategy(initial_equity=active_equity)
        df = pd.read_pickle(data_path)
        df_feat = strat.compute_pit_features(df)
        all_dates = sorted(df_feat["date"].unique())
        target_date = trading_date if trading_date in all_dates else all_dates[-1]

        day_df = df_feat[df_feat["date"] == target_date].copy()
        eligible = day_df[day_df["pit_eligible"]].sort_values("pit_score", ascending=False)
        top_candidates = eligible.head(strat.max_concurrent_positions)

        orders = []
        for rank_idx, (_, row) in enumerate(top_candidates.iterrows(), 1):
            sym = row["symbol"]
            open_px = row.get("open", row.get("prev_close", 0))
            entry_price = open_px * (1.0 + strat.entry_slippage_pct)
            initial_sl = max(row.get("prev_close", entry_price) * 0.998, entry_price * (1.0 - strat.initial_stop_loss_pct))
            pos_cap = min(active_equity * strat.max_position_weight, strat.max_position_cap_inr)
            shares = int(pos_cap / entry_price) if entry_price > 0 else 0
            allocated_cap = shares * entry_price

            orders.append({
                "Rank": f"#{rank_idx}", "Symbol": sym, "Entry": round(entry_price, 2),
                "SL": round(initial_sl, 2), "Shares": shares, "Capital": round(allocated_cap, 2)
            })

        orders_df = pd.DataFrame(orders)
        orders_df.to_csv("daily_live_scan_orders.csv", index=False)
        return orders_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live 09:30 AM Mid-Cap Strategy Scanner")
    parser.add_argument("--date", type=str, default=None, help="Trading date YYYY-MM-DD")
    parser.add_argument("--equity", type=float, default=10_000_000.0, help="Active equity in INR")
    parser.add_argument("--engine", type=str, default="ml_top3", choices=["ml_top3", "pit"], help="Strategy engine to run")
    parser.add_argument("--live", action="store_true", help="Force live market download")
    args = parser.parse_args()

    run_scanner(
        trading_date=args.date,
        active_equity=args.equity,
        engine=args.engine,
        force_live=args.live
    )
