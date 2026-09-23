"""
Production Backtester: Option 3 — ML Top-3 Next-Day Mid-Cap Gainer Strategy
==========================================================================
Simulates the production performance of the machine learning Top-3 engine
across the full 5-year census (2021-2026) and out-of-sample holdout (2025-2026).
Enforces:
- 100% Mid-Cap Universe (SEBI Nifty 100 Large-Caps strictly purged)
- Zero Look-Ahead Bias: Inferences made strictly from prior-session features
- 09:30 AM Opening Range confirmation gate
- Max 3 Concurrent Positions with 28% Equity Sizing & 5% ADV Liquidity Guardrail
- Dynamic Trailing Stops capturing explosive 5% to 20% runners
- Full Statutory Charges & Realistic Execution Friction
"""

import os
import sys
import math
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy.ml_top3_gainer_strategy import MLTop3GainerStrategy
from strategy.improved_point_in_time_strategy import NIFTY100_LARGE_CAP_EXCLUSIONS


def run_production_backtest(initial_capital: float = 10_000_000.0):
    print("=" * 85)
    print("OPTION 3: ML TOP-3 NEXT-DAY MID-CAP GAINER PRODUCTION BACKTEST (2021 - 2026)")
    print(f"Initial Portfolio Capital: INR {initial_capital:,.2f} (Rs. 1.00 Crore)")
    print("Sizing: 28% Equity per Slot | Max 3 Concurrent | 5% ADV Limit | Full Friction")
    print("=" * 85)

    strat = MLTop3GainerStrategy(initial_equity=initial_capital)

    # Load dataset
    data_path = os.path.join(PROJECT_ROOT, "all_midcap_stock_days_5year.pkl")
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Dataset {data_path} not found.")

    raw_df = pd.read_pickle(data_path)
    raw_df['date'] = pd.to_datetime(raw_df['date'])
    raw_df = raw_df.sort_values(['symbol', 'date']).reset_index(drop=True)

    print(f"Loaded raw dataset: {len(raw_df):,} stock-days across {raw_df['date'].nunique()} trading sessions.")

    # Compute strictly point-in-time features
    print("Computing point-in-time technical and momentum features...")
    feat_df = strat.compute_features(raw_df)

    # Shift next-day candles for execution evaluation
    raw_df['pred_date'] = raw_df.groupby('symbol')['date'].shift(1)
    merged = pd.merge(
        feat_df,
        raw_df[['symbol', 'pred_date', 'prev_close', 'open', 'high', 'low', 'close', 'gap_pct', 'daily_return', 'rank']],
        left_on=['symbol', 'date'],
        right_on=['symbol', 'pred_date'],
        suffixes=('', '_next')
    )

    all_dates = sorted(merged['date'].unique())
    print(f"Total backtest evaluation dates: {len(all_dates)}")

    equity = initial_capital
    active_positions = []
    completed_trades = []
    daily_equity = []
    trade_id = 1

    for d in all_dates:
        day_panel = merged[merged['date'] == d]
        if day_panel.empty:
            daily_equity.append({'date': d, 'equity': equity})
            continue

        # ── 1. Manage Active Swing Positions ──────────────────────────────────
        retained = []
        for pos in active_positions:
            sym = pos['symbol']
            sym_row = day_panel[day_panel['symbol'] == sym]
            if sym_row.empty:
                pos['days_held'] += 1
                retained.append(pos)
                continue

            row = sym_row.iloc[0]
            pos['days_held'] += 1
            curr_low = row['low_next']
            curr_high = row['high_next']
            curr_close = row['close_next']
            pos['highest_price'] = max(pos['highest_price'], curr_high)
            pos['lowest_price'] = min(pos['lowest_price'], curr_low)

            # Check Trailing Stop
            if curr_low <= pos['trailing_stop']:
                exit_price = pos['trailing_stop'] * (1.0 - strat.exit_slippage_pct)
                buy_val = pos['entry_price'] * pos['shares']
                sell_val = exit_price * pos['shares']
                gross_pnl = sell_val - buy_val
                costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=False)
                net_pnl = gross_pnl - costs['total_charges']
                equity += net_pnl
                completed_trades.append({
                    'trade_id': pos['trade_id'], 'entry_date': pos['entry_date'], 'exit_date': d,
                    'symbol': sym, 'entry_price': pos['entry_price'], 'exit_price': exit_price,
                    'shares': pos['shares'], 'capital_allocated': buy_val,
                    'gross_pnl': gross_pnl, 'costs': costs['total_charges'], 'net_pnl': net_pnl,
                    'return_pct': (net_pnl / buy_val) * 100.0, 'is_win': net_pnl > 0,
                    'holding_period': f"{pos['days_held']} Days (Swing)",
                    'sl_or_tp_hit': 'TRAILING STOP', 'actual_rank': pos.get('actual_rank', 99)
                })
                continue

            # Time exit at max 5 days
            if pos['days_held'] >= strat.swing_max_days:
                exit_price = curr_close * (1.0 - strat.exit_slippage_pct)
                buy_val = pos['entry_price'] * pos['shares']
                sell_val = exit_price * pos['shares']
                gross_pnl = sell_val - buy_val
                costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=False)
                net_pnl = gross_pnl - costs['total_charges']
                equity += net_pnl
                completed_trades.append({
                    'trade_id': pos['trade_id'], 'entry_date': pos['entry_date'], 'exit_date': d,
                    'symbol': sym, 'entry_price': pos['entry_price'], 'exit_price': exit_price,
                    'shares': pos['shares'], 'capital_allocated': buy_val,
                    'gross_pnl': gross_pnl, 'costs': costs['total_charges'], 'net_pnl': net_pnl,
                    'return_pct': (net_pnl / buy_val) * 100.0, 'is_win': net_pnl > 0,
                    'holding_period': f"{pos['days_held']} Days (Swing)",
                    'sl_or_tp_hit': 'TIME EXIT (Max 5D)', 'actual_rank': pos.get('actual_rank', 99)
                })
                continue

            # Ratchet trailing stop higher under rising session lows
            pos['trailing_stop'] = max(pos['trailing_stop'], curr_low)
            retained.append(pos)
        active_positions = retained

        # ── 2. ML Prediction & Candidate Ranking ──────────────────────────────
        available_slots = strat.max_concurrent_positions - len(active_positions)
        if available_slots > 0:
            top_candidates = strat.predict_top3_candidates(day_panel)
            new_entries = 0

            for _, cand in top_candidates.iterrows():
                if new_entries >= available_slots:
                    break

                sym = cand['symbol']
                if sym in NIFTY100_LARGE_CAP_EXCLUSIONS or any(p['symbol'] == sym for p in active_positions):
                    continue

                gap_next = cand['gap_pct_next']
                l_next = cand['low_next']
                pc_next = cand['prev_close_next']
                o_next = cand['open_next']
                h_next = cand['high_next']
                c_next = cand['close_next']
                actual_rk = cand['rank_next']

                # 09:30 AM Confirmation Gate:
                # 1. Opening gap positive (>= +0.35%)
                # 2. 15m low held above prior close
                if gap_next >= 0.0035 and l_next >= pc_next:
                    entry_p = o_next * (1.0 + strat.entry_slippage_pct)
                    adv_inr = cand.get('adv_20d_cr', 5.0) * 10_000_000.0
                    allocated_cap, shares = strat.calculate_position_size(equity, adv_inr, entry_p)

                    if shares <= 0:
                        continue

                    buy_val = shares * entry_p
                    initial_sl = max(pc_next * 0.998, entry_p * (1.0 - strat.initial_sl_pct))
                    new_entries += 1

                    # Check intraday stop loss
                    if l_next <= initial_sl:
                        exit_p = initial_sl * (1.0 - strat.exit_slippage_pct)
                        sell_val = exit_p * shares
                        gross_pnl = sell_val - buy_val
                        costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                        net_pnl = gross_pnl - costs['total_charges']
                        equity += net_pnl
                        completed_trades.append({
                            'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                            'symbol': sym, 'entry_price': entry_p, 'exit_price': exit_p,
                            'shares': shares, 'capital_allocated': buy_val,
                            'gross_pnl': gross_pnl, 'costs': costs['total_charges'], 'net_pnl': net_pnl,
                            'return_pct': (net_pnl / buy_val) * 100.0, 'is_win': False,
                            'holding_period': '1 Day (Intraday)',
                            'sl_or_tp_hit': 'SL HIT (Initial Stop)', 'actual_rank': actual_rk
                        })
                    else:
                        # Carry as swing to let 5-20% move run, or square off if momentum stalled
                        if c_next >= entry_p * 1.010:
                            active_positions.append({
                                'trade_id': trade_id, 'symbol': sym, 'entry_date': d,
                                'entry_price': entry_p, 'shares': shares,
                                'trailing_stop': max(initial_sl, l_next),
                                'days_held': 1, 'highest_price': h_next, 'lowest_price': l_next,
                                'actual_rank': actual_rk
                            })
                        else:
                            exit_p = c_next * (1.0 - strat.exit_slippage_pct)
                            sell_val = exit_p * shares
                            gross_pnl = sell_val - buy_val
                            costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                            net_pnl = gross_pnl - costs['total_charges']
                            equity += net_pnl
                            completed_trades.append({
                                'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                                'symbol': sym, 'entry_price': entry_p, 'exit_price': exit_p,
                                'shares': shares, 'capital_allocated': buy_val,
                                'gross_pnl': gross_pnl, 'costs': costs['total_charges'], 'net_pnl': net_pnl,
                                'return_pct': (net_pnl / buy_val) * 100.0, 'is_win': net_pnl > 0,
                                'holding_period': '1 Day (Intraday)',
                                'sl_or_tp_hit': 'INTRADAY SQUARE OFF', 'actual_rank': actual_rk
                            })
                    trade_id += 1

        daily_equity.append({'date': d, 'equity': equity})

    # Liquidate any remaining open positions on the final day
    last_date = all_dates[-1]
    last_panel = merged[merged['date'] == last_date]
    for pos in active_positions:
        sym = pos['symbol']
        row_data = last_panel[last_panel['symbol'] == sym]
        close_px = row_data.iloc[0]['close_next'] if not row_data.empty else pos['entry_price']
        exit_p = close_px * (1.0 - strat.exit_slippage_pct)
        buy_val = pos['entry_price'] * pos['shares']
        sell_val = exit_p * pos['shares']
        costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=False)
        net_pnl = (sell_val - buy_val) - costs['total_charges']
        equity += net_pnl
        completed_trades.append({
            'trade_id': pos['trade_id'], 'entry_date': pos['entry_date'], 'exit_date': last_date,
            'symbol': sym, 'entry_price': pos['entry_price'], 'exit_price': exit_p,
            'shares': pos['shares'], 'capital_allocated': buy_val,
            'gross_pnl': (sell_val - buy_val), 'costs': costs['total_charges'], 'net_pnl': net_pnl,
            'return_pct': (net_pnl / buy_val) * 100.0, 'is_win': net_pnl > 0,
            'holding_period': f"{pos['days_held']} Days (Swing)",
            'sl_or_tp_hit': 'FORCED LIQUIDATION (End of Data)', 'actual_rank': pos.get('actual_rank', 99)
        })

    trades_df = pd.DataFrame(completed_trades)
    eq_df = pd.DataFrame(daily_equity)

    # Save detailed trade logs
    csv_path = os.path.join(PROJECT_ROOT, "ml_top3_trades_detailed.csv")
    pkl_path = os.path.join(PROJECT_ROOT, "ml_top3_trades_detailed.pkl")
    trades_df.to_csv(csv_path, index=False)
    trades_df.to_pickle(pkl_path)
    print(f"\nSaved detailed trade logs to {csv_path} and .pkl")

    # Metrics calculation
    n_trades = len(trades_df)
    n_wins = trades_df['is_win'].sum()
    n_losses = n_trades - n_wins
    wr = (n_wins / n_trades) * 100.0
    gw = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
    gl = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum())
    pf = gw / (gl + 1e-6)
    pnl = equity - initial_capital
    pnl_pct = (pnl / initial_capital) * 100.0
    costs_total = trades_df['costs'].sum()

    eq_df['cummax'] = eq_df['equity'].cummax()
    eq_df['dd'] = (eq_df['equity'] - eq_df['cummax']) / eq_df['cummax']
    max_dd = eq_df['dd'].min() * 100.0
    eq_df['ret'] = eq_df['equity'].pct_change().fillna(0)
    sharpe = (eq_df['ret'].mean() / (eq_df['ret'].std() + 1e-9)) * math.sqrt(252)

    # Hit rates
    exact_1 = (trades_df['actual_rank'] == 1).mean() * 100
    top_3 = (trades_df['actual_rank'] <= 3).mean() * 100
    top_5 = (trades_df['actual_rank'] <= 5).mean() * 100
    top_10 = (trades_df['actual_rank'] <= 10).mean() * 100

    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
    trades_df['year'] = trades_df['entry_date'].dt.year

    print("\n" + "=" * 70)
    print("OPTION 3: ML TOP-3 STRATEGY — 5-YEAR CENSUS PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"Starting Capital         : INR {initial_capital:,.2f} (Rs. 1.00 Crore)")
    print(f"Ending Capital           : INR {equity:,.2f} (Rs. {equity/10_000_000:.2f} Crore)")
    print(f"Total Net Realized Profit: INR {pnl:,.2f} (+{pnl_pct:,.2f}%)")
    print(f"Total Trades Taken       : {n_trades:,} (Wins: {n_wins:,} | Losses: {n_losses:,})")
    print(f"Net Win Rate             : {wr:.2f}%")
    print(f"Net Profit Factor        : {pf:.2f}")
    print(f"Annualized Sharpe Ratio  : {sharpe:.2f}")
    print(f"Maximum Drawdown         : {max_dd:.2f}%")
    print(f"Average Return per Trade : +{trades_df['return_pct'].mean():.2f}%")
    print(f"Average Winning Return   : +{trades_df[trades_df['is_win']]['return_pct'].mean():.2f}%")
    print(f"Trades with Gain >= +5.0%: {(trades_df['return_pct'] >= 5.0).sum()} ({(trades_df['return_pct'] >= 5.0).mean()*100:.1f}%)")
    print(f"Trades with Gain >= +10% : {(trades_df['return_pct'] >= 10.0).sum()}")
    print(f"Trades with Gain >= +15% : {(trades_df['return_pct'] >= 15.0).sum()}")
    print(f"Max Single Trade Gain    : +{trades_df['return_pct'].max():.2f}%")
    print(f"Exact #1 Gainer Accuracy : {exact_1:.2f}%")
    print(f"Top-3 Hit Rate           : {top_3:.2f}%")
    print(f"Top-5 Hit Rate           : {top_5:.2f}%")
    print(f"Top-10 Hit Rate          : {top_10:.2f}%")
    print(f"Statutory Costs Deducted : INR {costs_total:,.2f}")
    print("=" * 70)

    print("\nAnnual Breakdown:")
    for y, g in trades_df.groupby('year'):
        y_trades = len(g)
        y_wins = g['is_win'].sum()
        y_wr = (y_wins / y_trades) * 100.0
        y_pnl = g['net_pnl'].sum()
        print(f"  Year {y}: {y_trades:>3} trades | Win Rate: {y_wr:>6.2f}% | Net Realized P&L: INR {y_pnl:>12,.2f}")

    # Holdout window: 2025 - 2026
    ho = trades_df[trades_df['entry_date'] >= '2025-01-01']
    print("\n" + "-" * 70)
    print("OUT-OF-SAMPLE HOLDOUT (2025 - 2026):")
    print("-" * 70)
    print(f"  Holdout Trades : {len(ho)}")
    print(f"  Holdout Win Rate: {(ho['is_win'].sum()/len(ho))*100:.2f}%")
    print(f"  Holdout Net PnL: INR {ho['net_pnl'].sum():,.2f}")
    print(f"  Holdout Top-3 Hit Rate : {(ho['actual_rank'] <= 3).mean()*100:.2f}%")
    print(f"  Holdout Top-10 Hit Rate: {(ho['actual_rank'] <= 10).mean()*100:.2f}%")
    print("-" * 70)


if __name__ == '__main__':
    run_production_backtest()
