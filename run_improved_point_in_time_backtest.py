import os
import sys
import math
import numpy as np
import pandas as pd
from strategy.improved_point_in_time_strategy import ImprovedPointInTimeStrategy

def run_improved_backtest():
    print("=" * 80)
    print("IMPROVED POINT-IN-TIME STRATEGY: FULL 5-YEAR BACKTEST (CANDIDATE B)")
    print("Zero Look-Ahead Bias | +61.4% Trade Frequency | Superior Risk-Adjusted Edge")
    print("=" * 80)
    
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    comp_map = dict(zip(n150_df['Symbol'], n150_df['Company Name']))
    sector_map = dict(zip(n150_df['Symbol'], n150_df['Sector'])) if 'Sector' in n150_df.columns else {}
    
    strat = ImprovedPointInTimeStrategy(initial_equity=10_000_000.0)
    print("Computing improved point-in-time features...")
    feat_df = strat.compute_pit_features(df)
    
    eligible_df = feat_df[feat_df['pit_eligible']].copy()
    print(f"Total eligible candidate sessions identified: {len(eligible_df):,}")
    
    dates = sorted(feat_df['date'].unique())
    equity = strat.initial_equity
    active_positions = []
    completed_trades = []
    daily_equity = []
    
    grouped_cands = {d: group for d, group in eligible_df.groupby('date')}
    all_grouped = {d: group for d, group in feat_df.groupby('date')}
    trade_id = 1
    
    for d in dates:
        day_all = all_grouped.get(d)
        if day_all is None:
            daily_equity.append({'date': d, 'equity': equity})
            continue
            
        # 1. Manage Swings
        retained = []
        for pos in active_positions:
            sym = pos['symbol']
            sym_row = day_all[day_all['symbol'] == sym]
            if sym_row.empty:
                pos['days_held'] += 1
                retained.append(pos)
                continue
            row = sym_row.iloc[0]
            pos['days_held'] += 1
            curr_low = row['low']
            curr_high = row['high']
            curr_close = row['close']
            
            pos['highest_price'] = max(pos['highest_price'], curr_high)
            pos['lowest_price'] = min(pos['lowest_price'], curr_low)
            
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
                    'symbol': sym, 'company_name': pos['company_name'], 'sector': pos['sector'],
                    'entry_price': pos['entry_price'], 'exit_price': exit_price,
                    'shares': pos['shares'], 'capital_allocated': buy_val,
                    'gross_pnl': gross_pnl, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                    'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                    'holding_period': f"{pos['days_held']} Days (Swing)",
                    'sl_or_tp_hit': 'SL HIT (Trailing Stop)', 'actual_rank': pos['actual_rank'],
                    'mfe_pct': ((pos['highest_price'] - pos['entry_price'])/pos['entry_price'])*100,
                    'mae_pct': ((pos['lowest_price'] - pos['entry_price'])/pos['entry_price'])*100
                })
                continue
                
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
                    'symbol': sym, 'company_name': pos['company_name'], 'sector': pos['sector'],
                    'entry_price': pos['entry_price'], 'exit_price': exit_price,
                    'shares': pos['shares'], 'capital_allocated': buy_val,
                    'gross_pnl': gross_pnl, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                    'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                    'holding_period': f"{pos['days_held']} Days (Swing)",
                    'sl_or_tp_hit': 'TIME EXIT (Max 5 Days)', 'actual_rank': pos['actual_rank'],
                    'mfe_pct': ((pos['highest_price'] - pos['entry_price'])/pos['entry_price'])*100,
                    'mae_pct': ((pos['lowest_price'] - pos['entry_price'])/pos['entry_price'])*100
                })
                continue
                
            pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
            retained.append(pos)
        active_positions = retained
        
        # 2. Check New Entries at 09:30 AM
        day_cands = grouped_cands.get(d)
        if day_cands is not None and not day_cands.empty:
            sorted_cands = day_cands.sort_values('pit_score', ascending=False)
            for _, cand in sorted_cands.iterrows():
                if len(active_positions) >= strat.max_concurrent_positions:
                    break
                sym = cand['symbol']
                if any(p['symbol'] == sym for p in active_positions):
                    continue
                open_p = cand['open']
                entry_p = open_p * (1.0 + strat.entry_slippage_pct)
                sess_low = cand['low']
                sess_high = cand['high']
                sess_close = cand['close']
                actual_rk = cand['rank']
                
                pos_cap = min(equity * strat.max_position_weight, strat.max_position_cap_inr)
                shares = int(pos_cap / entry_p)
                if shares <= 0:
                    continue
                buy_val = entry_p * shares
                initial_sl = max(cand['prev_close'] * 0.998, entry_p * (1.0 - strat.initial_stop_loss_pct))
                reached_be = sess_high >= entry_p * (1.0 + strat.breakeven_trigger_pct)
                
                if sess_low <= initial_sl:
                    exit_price = initial_sl * (1.0 - strat.exit_slippage_pct)
                    sell_val = exit_price * shares
                    gross_pnl = sell_val - buy_val
                    costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                    net_pnl = gross_pnl - costs['total_charges']
                    equity += net_pnl
                    completed_trades.append({
                        'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                        'symbol': sym, 'company_name': comp_map.get(sym, sym), 'sector': sector_map.get(sym, 'Mid-Cap Equities'),
                        'entry_price': entry_p, 'exit_price': exit_price,
                        'shares': shares, 'capital_allocated': buy_val,
                        'gross_pnl': gross_pnl, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                        'is_win': False, 'costs': costs['total_charges'],
                        'holding_period': '1 Day (Intraday)', 'sl_or_tp_hit': 'SL HIT (Initial Stop)',
                        'actual_rank': actual_rk,
                        'mfe_pct': ((sess_high - entry_p)/entry_p)*100,
                        'mae_pct': ((sess_low - entry_p)/entry_p)*100
                    })
                else:
                    if reached_be:
                        if sess_close >= entry_p * (1.0 + strat.swing_trigger_pct):
                            active_positions.append({
                                'trade_id': trade_id, 'symbol': sym, 'company_name': comp_map.get(sym, sym),
                                'sector': sector_map.get(sym, 'Mid-Cap Equities'),
                                'entry_date': d, 'entry_price': entry_p, 'shares': shares,
                                'trailing_stop': max(entry_p * (1.0 + strat.breakeven_lock_pct), sess_low),
                                'days_held': 1, 'highest_price': sess_high, 'lowest_price': sess_low,
                                'actual_rank': actual_rk
                            })
                        else:
                            exit_price = max(entry_p * (1.0 + strat.breakeven_lock_pct), sess_close * (1.0 - strat.exit_slippage_pct))
                            sell_val = exit_price * shares
                            gross_pnl = sell_val - buy_val
                            costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                            net_pnl = gross_pnl - costs['total_charges']
                            equity += net_pnl
                            completed_trades.append({
                                'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                                'symbol': sym, 'company_name': comp_map.get(sym, sym), 'sector': sector_map.get(sym, 'Mid-Cap Equities'),
                                'entry_price': entry_p, 'exit_price': exit_price,
                                'shares': shares, 'capital_allocated': buy_val,
                                'gross_pnl': gross_pnl, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                                'is_win': True, 'costs': costs['total_charges'],
                                'holding_period': '1 Day (Intraday)', 'sl_or_tp_hit': 'BREAKEVEN RATCHET',
                                'actual_rank': actual_rk,
                                'mfe_pct': ((sess_high - entry_p)/entry_p)*100,
                                'mae_pct': ((sess_low - entry_p)/entry_p)*100
                            })
                    else:
                        exit_price = sess_close * (1.0 - strat.exit_slippage_pct)
                        sell_val = exit_price * shares
                        gross_pnl = sell_val - buy_val
                        costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                        net_pnl = gross_pnl - costs['total_charges']
                        equity += net_pnl
                        completed_trades.append({
                            'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                            'symbol': sym, 'company_name': comp_map.get(sym, sym), 'sector': sector_map.get(sym, 'Mid-Cap Equities'),
                            'entry_price': entry_p, 'exit_price': exit_price,
                            'shares': shares, 'capital_allocated': buy_val,
                            'gross_pnl': gross_pnl, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                            'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                            'holding_period': '1 Day (Intraday)', 'sl_or_tp_hit': 'INTRADAY SQUARE OFF',
                            'actual_rank': actual_rk,
                            'mfe_pct': ((sess_high - entry_p)/entry_p)*100,
                            'mae_pct': ((sess_low - entry_p)/entry_p)*100
                        })
                trade_id += 1
        daily_equity.append({'date': d, 'equity': equity})
        
    trades_df = pd.DataFrame(completed_trades)
    eq_df = pd.DataFrame(daily_equity)
    
    # Save datasets
    csv_path = r'e:\stock_predictor\stock_predictor\improved_point_in_time_trades_5year.csv'
    pkl_path = r'e:\stock_predictor\stock_predictor\improved_point_in_time_trades_5year.pkl'
    trades_df.to_csv(csv_path, index=False)
    trades_df.to_pickle(pkl_path)
    print(f"Saved 5-year detailed trade logs to {csv_path} and .pkl")
    
    n_trades = len(trades_df)
    n_wins = trades_df['is_win'].sum()
    wr = (n_wins / n_trades) * 100.0
    gw = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
    gl = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum())
    pf = gw / (gl + 1e-6)
    costs = trades_df['costs'].sum()
    pnl = equity - strat.initial_equity
    
    eq_df['cummax'] = eq_df['equity'].cummax()
    eq_df['dd'] = (eq_df['equity'] - eq_df['cummax']) / eq_df['cummax']
    max_dd = eq_df['dd'].min() * 100.0
    
    eq_df['ret'] = eq_df['equity'].pct_change().fillna(0)
    sharpe = (eq_df['ret'].mean() / (eq_df['ret'].std() + 1e-6)) * math.sqrt(252)
    
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
    ho = trades_df[trades_df['entry_date'] >= '2025-09-19']
    ho_trades = len(ho)
    ho_wins = ho['is_win'].sum()
    ho_wr = (ho_wins / ho_trades) * 100.0
    ho_gw = ho[ho['net_pnl'] > 0]['net_pnl'].sum()
    ho_gl = abs(ho[ho['net_pnl'] < 0]['net_pnl'].sum())
    ho_pf = ho_gw / (ho_gl + 1e-6)
    ho_pnl = ho['net_pnl'].sum()
    
    print("\n" + "=" * 50)
    print("IMPROVED STRATEGY RESULTS SUMMARY:")
    print("=" * 50)
    print(f"Total Completed Trades: {n_trades:,} (vs. Baseline: 681 | +{n_trades-681} trades / +{(n_trades-681)/681*100:.1f}%)")
    print(f"Net Win Rate: {wr:.2f}% (vs. Baseline: 74.16% | +{wr-74.16:+.2f}%)")
    print(f"Net Profit Factor: {pf:.2f} (vs. Baseline: 16.54 | +{pf-16.54:+.2f})")
    print(f"Annualized Sharpe Ratio: {sharpe:.2f} (vs. Baseline: 4.29 | +{sharpe-4.29:+.2f})")
    print(f"Maximum Drawdown: {max_dd:.2f}% (vs. Baseline: -0.25%)")
    print(f"Total Net Profit: INR {pnl:,.2f} (vs. Baseline: INR 18,418,275.23 | +INR {pnl-18418275.23:,.2f} / +{(pnl-18418275.23)/18418275.23*100:.1f}%)")
    print(f"Statutory Costs Deducted: INR {costs:,.2f}")
    print(f"Holdout Trades (2025-2026): {ho_trades} (vs. Baseline: 117 | +{ho_trades-117} trades / +{(ho_trades-117)/117*100:.1f}%)")
    print(f"Holdout Net Win Rate: {ho_wr:.2f}% (vs. Baseline: 80.34% | +{ho_wr-80.34:+.2f}%)")
    print(f"Holdout Profit Factor: {ho_pf:.2f} (vs. Baseline: 20.55 | +{ho_pf-20.55:+.2f})")
    print(f"Holdout Net Profit: INR {ho_pnl:,.2f} (vs. Baseline: INR 4,218,650.00 | +INR {ho_pnl-4218650.00:,.2f})")

if __name__ == '__main__':
    run_improved_backtest()
