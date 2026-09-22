import os
import sys
import math
import numpy as np
import pandas as pd
from strategy.improved_point_in_time_strategy import ImprovedPointInTimeStrategy

def run_recovery_research():
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    strat = ImprovedPointInTimeStrategy(initial_equity=10_000_000.0)
    feat_df = strat.compute_pit_features(df)
    eligible_df = feat_df[feat_df['pit_eligible']].copy()
    
    dates = sorted(feat_df['date'].unique())
    all_grouped = {d: group for d, group in feat_df.groupby('date')}
    grouped_cands = {d: group for d, group in eligible_df.groupby('date')}
    
    def simulate_variation(
        pos_weight=0.10,
        max_pos_cap=None,
        use_conviction_sizing=False,
        swing_max_days=5,
        swing_trigger=0.012,
        trail_mode='daily_low'
    ):
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
                
                # Exit via trailing stop
                if curr_low <= pos['trailing_stop']:
                    exit_price = pos['trailing_stop'] * 0.998
                    buy_val = pos['entry_price'] * pos['shares']
                    sell_val = exit_price * pos['shares']
                    gross_pnl = sell_val - buy_val
                    costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=False)
                    net_pnl = gross_pnl - costs['total_charges']
                    equity += net_pnl
                    completed.append({
                        'trade_id': pos['trade_id'], 'entry_date': pos['entry_date'], 'exit_date': d,
                        'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                        'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                        'capital': buy_val, 'days_held': pos['days_held']
                    })
                    continue
                    
                # Exit via max days
                if pos['days_held'] >= swing_max_days:
                    exit_price = curr_close * 0.998
                    buy_val = pos['entry_price'] * pos['shares']
                    sell_val = exit_price * pos['shares']
                    gross_pnl = sell_val - buy_val
                    costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=False)
                    net_pnl = gross_pnl - costs['total_charges']
                    equity += net_pnl
                    completed.append({
                        'trade_id': pos['trade_id'], 'entry_date': pos['entry_date'], 'exit_date': d,
                        'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                        'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                        'capital': buy_val, 'days_held': pos['days_held']
                    })
                    continue
                    
                # Update trailing stop
                if trail_mode == 'daily_low':
                    pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
                elif trail_mode == 'breakeven_then_low':
                    pos['trailing_stop'] = max(pos['trailing_stop'], pos['entry_price'] * 1.01)
                    if pos['days_held'] >= 2:
                        pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
                        
                retained.append(pos)
            active_positions = retained
            
            day_cands = grouped_cands.get(d)
            if day_cands is not None and not day_cands.empty:
                sorted_cands = day_cands.sort_values('pit_score', ascending=False)
                rank_idx = 0
                for _, cand in sorted_cands.iterrows():
                    if len(active_positions) >= 8:
                        break
                    sym = cand['symbol']
                    if any(p['symbol'] == sym for p in active_positions):
                        continue
                    open_p = cand['open']
                    entry_p = open_p * 1.002
                    sess_low = cand['low']
                    sess_high = cand['high']
                    sess_close = cand['close']
                    
                    # Sizing logic
                    if use_conviction_sizing:
                        # Rank 1 gets 12.5%, Rank 2 gets 10%, Rank 3+ gets 7.5%
                        cur_w = 0.125 if rank_idx == 0 else (0.10 if rank_idx == 1 else 0.075)
                    else:
                        cur_w = pos_weight
                        
                    pos_cap = equity * cur_w
                    if max_pos_cap is not None:
                        pos_cap = min(pos_cap, max_pos_cap)
                    shares = int(pos_cap / entry_p)
                    if shares <= 0:
                        continue
                    buy_val = entry_p * shares
                    initial_sl = max(cand['prev_close'] * 0.998, entry_p * 0.982)
                    reached_be = sess_high >= entry_p * 1.010
                    
                    if sess_low <= initial_sl:
                        exit_price = initial_sl * 0.998
                        sell_val = exit_price * shares
                        gross_pnl = sell_val - buy_val
                        costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                        net_pnl = gross_pnl - costs['total_charges']
                        equity += net_pnl
                        completed.append({
                            'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                            'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                            'is_win': False, 'costs': costs['total_charges'],
                            'capital': buy_val, 'days_held': 1
                        })
                    else:
                        if reached_be:
                            if sess_close >= entry_p * (1.0 + swing_trigger):
                                active_positions.append({
                                    'trade_id': trade_id, 'symbol': sym, 'entry_date': d,
                                    'entry_price': entry_p, 'shares': shares,
                                    'trailing_stop': max(entry_p * 1.002, sess_low),
                                    'days_held': 1, 'highest_price': sess_high, 'lowest_price': sess_low
                                })
                            else:
                                exit_price = max(entry_p * 1.002, sess_close * 0.998)
                                sell_val = exit_price * shares
                                gross_pnl = sell_val - buy_val
                                costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                                net_pnl = gross_pnl - costs['total_charges']
                                equity += net_pnl
                                completed.append({
                                    'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                                    'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                                    'is_win': True, 'costs': costs['total_charges'],
                                    'capital': buy_val, 'days_held': 1
                                })
                        else:
                            exit_price = sess_close * 0.998
                            sell_val = exit_price * shares
                            gross_pnl = sell_val - buy_val
                            costs = strat.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
                            net_pnl = gross_pnl - costs['total_charges']
                            equity += net_pnl
                            completed.append({
                                'trade_id': trade_id, 'entry_date': d, 'exit_date': d,
                                'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                                'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                                'capital': buy_val, 'days_held': 1
                            })
                    trade_id += 1
                    rank_idx += 1
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
        ho = tdf[tdf['entry_date'] >= '2025-09-19']
        ho_wr = (ho['is_win'].sum() / len(ho)) * 100.0 if len(ho) > 0 else 0
        ho_gw = ho[ho['net_pnl'] > 0]['net_pnl'].sum()
        ho_gl = abs(ho[ho['net_pnl'] < 0]['net_pnl'].sum())
        ho_pf = ho_gw / (ho_gl + 1e-6) if ho_gl > 0 else 0
        ho_pnl = ho['net_pnl'].sum() if len(ho) > 0 else 0
        
        avg_win = tdf[tdf['is_win']]['net_pnl'].mean()
        avg_loss = abs(tdf[~tdf['is_win']]['net_pnl'].mean())
        
        return {
            'trades': len(tdf),
            'win_rate': wr,
            'pf': pf,
            'sharpe': sharpe,
            'max_dd': max_dd,
            'net_pnl': pnl,
            'ending_eq': equity,
            'return_pct': (pnl / 10_000_000.0) * 100.0,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'ho_trades': len(ho),
            'ho_wr': ho_wr,
            'ho_pf': ho_pf,
            'ho_pnl': ho_pnl
        }
        
    variations = [
        ('1. Current Fixed Strategy (Hard Cap 20L)', {'pos_weight': 0.10, 'max_pos_cap': 2_000_000.0}),
        ('2. Dynamic Compounding (10% Equity, Cap 1 Cr)', {'pos_weight': 0.10, 'max_pos_cap': 10_000_000.0}),
        ('3. Dynamic Compounding (12.5% Equity, Cap 1.5 Cr)', {'pos_weight': 0.125, 'max_pos_cap': 15_000_000.0}),
        ('4. Conviction-Based Sizing (Rank 1=12.5%, Rank 2=10%, Rank 3=7.5%)', {'use_conviction_sizing': True, 'max_pos_cap': 10_000_000.0}),
        ('5. Extended Swing Trailing (Max 7 Days)', {'pos_weight': 0.10, 'max_pos_cap': 10_000_000.0, 'swing_max_days': 7}),
        ('6. Full Dynamic Compounding + Extended Swing (Max 7 Days, Cap 2 Cr)', {'pos_weight': 0.125, 'max_pos_cap': 20_000_000.0, 'swing_max_days': 7}),
        ('7. Full Unconstrained Compounding (10% Equity, No Cap)', {'pos_weight': 0.10, 'max_pos_cap': None})
    ]
    
    print("=" * 110)
    print(f"{'Variation Name':<52} | {'Trades':<6} | {'WR (%)':<6} | {'PF':<6} | {'Sharpe':<6} | {'MaxDD':<7} | {'Net P&L (INR)':<15} | {'HO WR (%)':<9} | {'HO PF':<6}")
    print("=" * 110)
    
    results = []
    for name, p in variations:
        res = simulate_variation(**p)
        print(f"{name:<52} | {res['trades']:<6} | {res['win_rate']:<6.2f} | {res['pf']:<6.2f} | {res['sharpe']:<6.2f} | {res['max_dd']:<7.2f} | INR {res['net_pnl']:<10,.0f} | {res['ho_wr']:<9.2f} | {res['ho_pf']:<6.2f}")
        results.append({'name': name, **res})
        
    res_df = pd.DataFrame(results)
    res_df.to_csv(r'e:\stock_predictor\stock_predictor\return_recovery_results.csv', index=False)
    print("\nSaved return recovery results to return_recovery_results.csv")

if __name__ == '__main__':
    run_recovery_research()
