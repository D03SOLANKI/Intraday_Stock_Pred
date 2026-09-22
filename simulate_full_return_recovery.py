import os
import sys
import math
import numpy as np
import pandas as pd
from strategy.improved_point_in_time_strategy import ImprovedPointInTimeStrategy

def run_recovery_experiment():
    print("Loading data...")
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    strat = ImprovedPointInTimeStrategy(initial_equity=10_000_000.0)
    feat_df = strat.compute_pit_features(df)
    eligible_df = feat_df[feat_df['pit_eligible']].copy()
    
    dates = sorted(feat_df['date'].unique())
    all_grouped = {d: group for d, group in feat_df.groupby('date')}
    grouped_cands = {d: group for d, group in eligible_df.groupby('date')}
    
    def simulate(
        pos_weight=0.10,
        max_positions=8,
        max_pos_cap=None,
        use_conviction_sizing=False,
        swing_max_days=5,
        swing_trigger=0.012,
        trail_type='daily_low', # 'daily_low', 'prev2_low', 'atr_trail'
        adv_limit_pct=0.05
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
                pos['history_lows'].append(curr_low)
                
                # Trailing stop hit
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
                        'capital': buy_val, 'days_held': pos['days_held'],
                        'mfe_pct': ((pos['highest_price'] - pos['entry_price'])/pos['entry_price'])*100
                    })
                    continue
                    
                # Time exit
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
                        'capital': buy_val, 'days_held': pos['days_held'],
                        'mfe_pct': ((pos['highest_price'] - pos['entry_price'])/pos['entry_price'])*100
                    })
                    continue
                    
                # Update trailing stop based on trail_type
                if trail_type == 'daily_low':
                    pos['trailing_stop'] = max(pos['trailing_stop'], curr_low)
                elif trail_type == 'prev2_low':
                    # Trail 2-day lowest low to give room for runners
                    if len(pos['history_lows']) >= 2:
                        pos['trailing_stop'] = max(pos['trailing_stop'], min(pos['history_lows'][-2:]))
                    else:
                        pos['trailing_stop'] = max(pos['trailing_stop'], curr_low)
                        
                retained.append(pos)
            active_positions = retained
            
            day_cands = grouped_cands.get(d)
            if day_cands is not None and not day_cands.empty:
                sorted_cands = day_cands.sort_values('pit_score', ascending=False)
                rank_idx = 0
                for _, cand in sorted_cands.iterrows():
                    if len(active_positions) >= max_positions:
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
                    
                    if use_conviction_sizing:
                        cur_w = 0.20 if rank_idx == 0 else (0.15 if rank_idx == 1 else 0.10)
                    else:
                        cur_w = pos_weight
                        
                    pos_cap = equity * cur_w
                    if max_pos_cap is not None:
                        pos_cap = min(pos_cap, max_pos_cap)
                        
                    # ADV volume limit (max 5% of daily volume to ensure zero liquidity impact)
                    if adv_limit_pct is not None and pd.notnull(vol_20d) and vol_20d > 0:
                        max_adv_val = (vol_20d * adv_limit_pct) * entry_p
                        pos_cap = min(pos_cap, max_adv_val)
                        
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
                            'capital': buy_val, 'days_held': 1,
                            'mfe_pct': ((sess_high - entry_p)/entry_p)*100
                        })
                    else:
                        if reached_be:
                            if sess_close >= entry_p * (1.0 + swing_trigger):
                                active_positions.append({
                                    'trade_id': trade_id, 'symbol': sym, 'entry_date': d,
                                    'entry_price': entry_p, 'shares': shares,
                                    'trailing_stop': max(entry_p * 1.002, sess_low),
                                    'days_held': 1, 'highest_price': sess_high, 'lowest_price': sess_low,
                                    'history_lows': [sess_low]
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
                                    'capital': buy_val, 'days_held': 1,
                                    'mfe_pct': ((sess_high - entry_p)/entry_p)*100
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
                                'capital': buy_val, 'days_held': 1,
                                'mfe_pct': ((sess_high - entry_p)/entry_p)*100
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
        
        return {
            'trades': len(tdf),
            'win_rate': wr,
            'pf': pf,
            'sharpe': sharpe,
            'max_dd': max_dd,
            'net_pnl': pnl,
            'ending_eq': equity,
            'max_alloc': tdf['capital'].max(),
            'mean_alloc': tdf['capital'].mean(),
            'ho_trades': len(ho),
            'ho_wr': ho_wr,
            'ho_pf': ho_pf,
            'ho_pnl': ho_pnl
        }
        
    configs = [
        ('1. Current Fixed Strategy (Hard Cap 20L)', {'pos_weight': 0.10, 'max_pos_cap': 2_000_000.0, 'max_positions': 8}),
        ('2. Dynamic Compounding (15% Equity, Max 6 Pos)', {'pos_weight': 0.15, 'max_positions': 6, 'max_pos_cap': None, 'adv_limit_pct': 0.05}),
        ('3. Dynamic Compounding (20% Equity, Max 5 Pos)', {'pos_weight': 0.20, 'max_positions': 5, 'max_pos_cap': None, 'adv_limit_pct': 0.05}),
        ('4. Conviction Sizing (20% / 15% / 10%)', {'use_conviction_sizing': True, 'max_positions': 6, 'max_pos_cap': None, 'adv_limit_pct': 0.05}),
        ('5. Dynamic Compounding (15%) + Runner Trail (7 Days)', {'pos_weight': 0.15, 'max_positions': 6, 'max_pos_cap': None, 'swing_max_days': 7, 'trail_type': 'prev2_low', 'adv_limit_pct': 0.05}),
        ('6. High-Conviction Compounding (20%) + Runner Trail (7 Days)', {'pos_weight': 0.20, 'max_positions': 5, 'max_pos_cap': None, 'swing_max_days': 7, 'trail_type': 'prev2_low', 'adv_limit_pct': 0.05}),
        ('7. Institutional Super-Compounding (25% Equity, Max 4 Pos, 7 Days)', {'pos_weight': 0.25, 'max_positions': 4, 'max_pos_cap': None, 'swing_max_days': 7, 'trail_type': 'prev2_low', 'adv_limit_pct': 0.05})
    ]
    
    print("=" * 115)
    print(f"{'Configuration':<55} | {'Trades':<6} | {'WR (%)':<6} | {'PF':<6} | {'Sharpe':<6} | {'MaxDD':<7} | {'Net P&L (INR)':<15} | {'Ending Capital (INR)':<18}")
    print("=" * 115)
    
    for name, p in configs:
        res = simulate(**p)
        print(f"{name:<55} | {res['trades']:<6} | {res['win_rate']:<6.2f} | {res['pf']:<6.2f} | {res['sharpe']:<6.2f} | {res['max_dd']:<7.2f} | INR {res['net_pnl']:<12,.0f} | INR {res['ending_eq']:<15,.0f}")
        print(f"      [Alloc Max: INR {res['max_alloc']:,.0f} | Mean: INR {res['mean_alloc']:,.0f} | Holdout WR: {res['ho_wr']:.2f}% | Holdout P&L: INR {res['ho_pnl']:,.0f}]")

if __name__ == '__main__':
    run_recovery_experiment()
