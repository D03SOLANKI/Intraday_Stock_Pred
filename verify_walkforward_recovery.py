import os
import sys
import math
import numpy as np
import pandas as pd
from strategy.improved_point_in_time_strategy import ImprovedPointInTimeStrategy

def run_walkforward_check():
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    strat = ImprovedPointInTimeStrategy(initial_equity=10_000_000.0)
    feat_df = strat.compute_pit_features(df)
    eligible_df = feat_df[feat_df['pit_eligible']].copy()
    
    dates = sorted(feat_df['date'].unique())
    all_grouped = {d: group for d, group in feat_df.groupby('date')}
    grouped_cands = {d: group for d, group in eligible_df.groupby('date')}
    
    tiers = [
        ('Tier 1: Conservative Baseline (10% Cap 20L)', 0.10, 8, 2_000_000.0),
        ('Tier 2: Balanced Growth (15% Cap 1.5 Cr)', 0.15, 6, 15_000_000.0),
        ('Tier 3: Aggressive Compounding (20% Cap 2.5 Cr)', 0.20, 5, 25_000_000.0),
        ('Tier 4: High-Conviction Maximum Alpha (28% ADV 5%)', 0.28, 4, None)
    ]
    
    tier_results = []
    
    for t_name, pos_w, max_p, max_c in tiers:
        equity = 10_000_000.0
        active_positions = []
        completed = []
        daily_equity = []
        trade_id = 1
        
        for d in dates:
            day_all = all_grouped.get(d)
            if day_all is None:
                daily_equity.append({'date': d, 'equity': equity})
                continue
                
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
                    exit_price = pos['trailing_stop'] * 0.998
                    buy_val = pos['entry_price'] * pos['shares']
                    sell_val = exit_price * pos['shares']
                    costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=False)
                    net_pnl = (sell_val - buy_val) - costs['total_charges']
                    equity += net_pnl
                    completed.append({'trade_id': pos['trade_id'], 'entry_date': pos['entry_date'], 'exit_date': d, 'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100, 'is_win': net_pnl > 0, 'capital': buy_val})
                    continue
                    
                if pos['days_held'] >= 5:
                    exit_price = curr_close * 0.998
                    buy_val = pos['entry_price'] * pos['shares']
                    sell_val = exit_price * pos['shares']
                    costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=False)
                    net_pnl = (sell_val - buy_val) - costs['total_charges']
                    equity += net_pnl
                    completed.append({'trade_id': pos['trade_id'], 'entry_date': pos['entry_date'], 'exit_date': d, 'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100, 'is_win': net_pnl > 0, 'capital': buy_val})
                    continue
                    
                pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
                retained.append(pos)
            active_positions = retained
            
            day_cands = grouped_cands.get(d)
            if day_cands is not None and not day_cands.empty:
                sorted_cands = day_cands.sort_values('pit_score', ascending=False)
                for _, cand in sorted_cands.iterrows():
                    if len(active_positions) >= max_p:
                        break
                    sym = cand['symbol']
                    if any(p['symbol'] == sym for p in active_positions):
                        continue
                    open_p = cand['open']
                    entry_p = open_p * 1.002
                    sess_low = cand['low']
                    sess_high = cand['high']
                    sess_close = cand['close']
                    vol_20d = cand.get('vol_20d', 500_000)
                    
                    pos_cap = equity * pos_w
                    if max_c is not None:
                        pos_cap = min(pos_cap, max_c)
                    if pd.notnull(vol_20d) and vol_20d > 0:
                        pos_cap = min(pos_cap, vol_20d * 0.05 * entry_p) # 5% ADV limit
                        
                    shares = int(pos_cap / entry_p)
                    if shares <= 0:
                        continue
                    buy_val = entry_p * shares
                    initial_sl = max(cand['prev_close'] * 0.998, entry_p * 0.982)
                    reached_be = sess_high >= entry_p * 1.010
                    
                    if sess_low <= initial_sl:
                        exit_price = initial_sl * 0.998
                        sell_val = exit_price * shares
                        costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                        net_pnl = (sell_val - buy_val) - costs['total_charges']
                        equity += net_pnl
                        completed.append({'trade_id': trade_id, 'entry_date': d, 'exit_date': d, 'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100, 'is_win': False, 'capital': buy_val})
                    else:
                        if reached_be:
                            if sess_close >= entry_p * 1.012:
                                active_positions.append({
                                    'trade_id': trade_id, 'symbol': sym, 'entry_date': d,
                                    'entry_price': entry_p, 'shares': shares,
                                    'trailing_stop': max(entry_p * 1.002, sess_low),
                                    'days_held': 1, 'highest_price': sess_high,
                                    'lowest_price': sess_low
                                })
                            else:
                                exit_price = max(entry_p * 1.002, sess_close * 0.998)
                                sell_val = exit_price * shares
                                costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                                net_pnl = (sell_val - buy_val) - costs['total_charges']
                                equity += net_pnl
                                completed.append({'trade_id': trade_id, 'entry_date': d, 'exit_date': d, 'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100, 'is_win': True, 'capital': buy_val})
                        else:
                            exit_price = sess_close * 0.998
                            sell_val = exit_price * shares
                            costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                            net_pnl = (sell_val - buy_val) - costs['total_charges']
                            equity += net_pnl
                            completed.append({'trade_id': trade_id, 'entry_date': d, 'exit_date': d, 'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100, 'is_win': net_pnl > 0, 'capital': buy_val})
                    trade_id += 1
            daily_equity.append({'date': d, 'equity': equity})
            
        tdf = pd.DataFrame(completed)
        eq_df = pd.DataFrame(daily_equity)
        eq_df['cummax'] = eq_df['equity'].cummax()
        eq_df['dd'] = (eq_df['equity'] - eq_df['cummax']) / eq_df['cummax']
        max_dd = eq_df['dd'].min() * 100.0
        wr = (tdf['is_win'].sum() / len(tdf)) * 100.0
        gw = tdf[tdf['net_pnl'] > 0]['net_pnl'].sum()
        gl = abs(tdf[tdf['net_pnl'] < 0]['net_pnl'].sum())
        pf = gw / (gl + 1e-6)
        pnl = equity - 10_000_000.0
        eq_df['ret'] = eq_df['equity'].pct_change().fillna(0)
        sharpe = (eq_df['ret'].mean() / (eq_df['ret'].std() + 1e-6)) * math.sqrt(252)
        
        tdf['entry_date'] = pd.to_datetime(tdf['entry_date'])
        
        # Yearly Breakdown
        tdf['year'] = tdf['entry_date'].dt.year
        yr_stats = {}
        for y, group in tdf.groupby('year'):
            yr_stats[y] = {
                'trades': len(group),
                'wr': (group['is_win'].sum() / len(group)) * 100.0,
                'pnl': group['net_pnl'].sum()
            }
            
        # Holdout
        ho = tdf[tdf['entry_date'] >= '2025-09-19']
        ho_wr = (ho['is_win'].sum() / len(ho)) * 100.0 if len(ho) > 0 else 0
        ho_pnl = ho['net_pnl'].sum() if len(ho) > 0 else 0
        
        tier_results.append({
            'tier': t_name, 'trades': len(tdf), 'wr': wr, 'pf': pf, 'sharpe': sharpe,
            'max_dd': max_dd, 'pnl': pnl, 'ending_eq': equity, 'ho_trades': len(ho),
            'ho_wr': ho_wr, 'ho_pnl': ho_pnl, 'yr_stats': yr_stats,
            'max_alloc': tdf['capital'].max(), 'mean_alloc': tdf['capital'].mean()
        })
        
    res_df = pd.DataFrame(tier_results)
    res_df.to_pickle(r'e:\stock_predictor\stock_predictor\walkforward_recovery_tiers.pkl')
    
    print("\n" + "=" * 115)
    print(f"{'Tier Name':<50} | {'Trades':<6} | {'WR (%)':<6} | {'PF':<6} | {'Sharpe':<6} | {'MaxDD':<7} | {'Net P&L (INR)':<15} | {'Ending Capital (INR)':<18}")
    print("=" * 115)
    for r in tier_results:
        print(f"{r['tier']:<50} | {r['trades']:<6} | {r['wr']:<6.2f} | {r['pf']:<6.2f} | {r['sharpe']:<6.2f} | {r['max_dd']:<7.2f} | INR {r['pnl']:<12,.0f} | INR {r['ending_eq']:<15,.0f}")
        print(f"      [Max Alloc: INR {r['max_alloc']:,.0f} | Holdout WR: {r['ho_wr']:.2f}% | Holdout P&L: INR {r['ho_pnl']:,.0f}]")
        print("      Yearly P&L:")
        for y, ys in r['yr_stats'].items():
            print(f"        {y}: {ys['trades']} trades | WR {ys['wr']:.1f}% | P&L: INR {ys['pnl']:,.0f}")

if __name__ == '__main__':
    run_walkforward_check()
