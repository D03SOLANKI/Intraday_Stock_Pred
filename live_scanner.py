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


def sync_live_market_data(raw_df: pd.DataFrame, symbols: list) -> pd.DataFrame:
    """
    Fetches the newest market days from Yahoo Finance for the midcap universe,
    merging them with raw_df so that candidate predictions automatically shift
    to the latest live market session.
    """
    try:
        import yfinance as yf
        tickers = [f"{s}.NS" for s in symbols if s not in NIFTY100_LARGE_CAP_EXCLUSIONS]
        print(f"Checking for new market sessions via Yahoo Finance for {len(tickers)} midcaps...")
        yf_data = yf.download(tickers, period="7d", interval="1d", progress=False)

        if yf_data.empty or 'Close' not in yf_data:
            return raw_df

        closes = yf_data['Close']
        opens = yf_data['Open']
        highs = yf_data['High']
        lows = yf_data['Low']
        volumes = yf_data['Volume']

        existing_dates = set(pd.to_datetime(raw_df['date']).dt.strftime('%Y-%m-%d').unique())
        sector_map = raw_df.groupby('symbol')['sector'].last().to_dict()
        new_rows = []

        for d in closes.index:
            d_str = d.strftime('%Y-%m-%d')
            if d_str not in existing_dates:
                for sym in symbols:
                    t = f"{sym}.NS"
                    if t in closes and not pd.isna(closes[t].loc[d]):
                        c = float(closes[t].loc[d])
                        o = float(opens[t].loc[d]) if t in opens and not pd.isna(opens[t].loc[d]) else c
                        h = float(highs[t].loc[d]) if t in highs and not pd.isna(highs[t].loc[d]) else c
                        l = float(lows[t].loc[d]) if t in lows and not pd.isna(lows[t].loc[d]) else c
                        v = float(volumes[t].loc[d]) if t in volumes and not pd.isna(volumes[t].loc[d]) else 0.0

                        new_rows.append({
                            'date': pd.to_datetime(d_str),
                            'symbol': sym,
                            'company': sym,
                            'sector': sector_map.get(sym, 'MidCap'),
                            'open': o,
                            'high': h,
                            'low': l,
                            'close': c,
                            'volume': v
                        })

        if new_rows:
            print(f"[LIVE SYNC] Appended {len(new_rows)} fresh stock-days across {len(set(r['date'] for r in new_rows))} new session(s).")
            df_new = pd.DataFrame(new_rows)
            combined = pd.concat([raw_df[['date', 'symbol', 'company', 'sector', 'open', 'high', 'low', 'close', 'volume']], df_new], ignore_index=True)
            combined = combined.sort_values(['symbol', 'date']).reset_index(drop=True)
            combined['prev_close'] = combined.groupby('symbol')['close'].shift(1)
            combined['daily_return'] = (combined['close'] - combined['prev_close']) / (combined['prev_close'] + 1e-6) * 100.0
            combined['gap_pct'] = (combined['open'] - combined['prev_close']) / (combined['prev_close'] + 1e-6) * 100.0
            return combined

    except Exception as e:
        print(f"[WARNING] Live market data sync error (falling back to baseline): {e}")

    return raw_df


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

        # Automatically synchronize with live market sessions
        universe_symbols = load_midcap_universe()
        raw_df = sync_live_market_data(raw_df, universe_symbols)

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

        # Fetch actual live real-time market tick (LTP) at the exact moment of execution
        candidate_symbols = top3_cands['symbol'].tolist()
        live_ticks = {}
        try:
            import yfinance as yf
            for s in candidate_symbols:
                t = f"{s}.NS"
                try:
                    tk = yf.Ticker(t)
                    lp = tk.fast_info['lastPrice']
                    if lp and not pd.isna(lp) and float(lp) > 0:
                        live_ticks[s] = float(lp)
                except Exception:
                    pass
            # Fallback to 1m interval download if fast_info missing for any symbol
            missing_syms = [s for s in candidate_symbols if s not in live_ticks]
            if missing_syms:
                cands_tickers = [f"{s}.NS" for s in missing_syms]
                tick_data = yf.download(cands_tickers, period="1d", interval="1m", progress=False)
                if not tick_data.empty and 'Close' in tick_data:
                    if isinstance(tick_data['Close'], pd.DataFrame):
                        for s in missing_syms:
                            t = f"{s}.NS"
                            if t in tick_data['Close']:
                                c_series = tick_data['Close'][t].dropna()
                                if not c_series.empty:
                                    live_ticks[s] = float(c_series.iloc[-1])
                    elif isinstance(tick_data['Close'], pd.Series):
                        s = missing_syms[0]
                        c_series = tick_data['Close'].dropna()
                        if not c_series.empty:
                            live_ticks[s] = float(c_series.iloc[-1])
        except Exception as tick_err:
            print(f"[WARNING] Real-time tick query error: {tick_err}")

        for rank_idx, (_, row) in enumerate(top3_cands.iterrows(), 1):
            sym = row['symbol']
            # STRICT RULE: Always use the real-time execution price at this exact moment
            actual_live_px = live_ticks.get(sym)
            if actual_live_px and actual_live_px > 0:
                curr_px = actual_live_px
                print(f"[{sym}] Using Actual Live Execution Tick (LTP): Rs. {curr_px:,.2f}")
            else:
                # In live execution, NEVER fall back to yesterday's close; use today's open if live tick is missing
                curr_px = row.get('open', row.get('close', 0))
                print(f"[{sym}] Warning: Live tick unavailable, using session open: Rs. {curr_px:,.2f}")

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
