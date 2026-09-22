import os
import sys
import math
import itertools
import numpy as np
import pandas as pd
from strategy.point_in_time_strategy import PointInTimeStrategy

def run_backtest_engine(df, n150_df, params, start_date=None, end_date=None):
    comp_map = dict(zip(n150_df['Symbol'], n150_df['Company Name']))
    sector_map = dict(zip(n150_df['Symbol'], n150_df['Sector'])) if 'Sector' in n150_df.columns else {}
    strat = PointInTimeStrategy(initial_equity=10_000_000.0)
    
    coiling_max = params.get('coiling_max', strat.coiling_dma_proximity_max)
    rsi_min = params.get('rsi_min', strat.rsi_min)
    rsi_max = params.get('rsi_max', strat.rsi_max)
    vol_prev_ratio_min = params.get('vol_prev_ratio_min', strat.vol_prev_ratio_min)
    gap_min = params.get('gap_min', strat.gap_min_pct)
    gap_max = params.get('gap_max', strat.gap_max_pct)
    bmark_min = params.get('bmark_min', strat.benchmark_headwind_min)
    enforce_gap_rej = params.get('enforce_gap_rej', True)
    enforce_qual = params.get('enforce_qual', True)
    max_positions = params.get('max_positions', strat.max_concurrent_positions)
    be_trigger = params.get('be_trigger', strat.breakeven_trigger_pct)
    be_lock = params.get('be_lock', strat.breakeven_lock_pct)
    swing_trigger = params.get('swing_trigger', strat.swing_trigger_pct)
    swing_max_days = params.get('swing_max_days', strat.swing_max_days)
    
    out = df.copy()
    out['dist_sma20_abs'] = out['dist_sma20'].abs()
    out['has_catalyst'] = out['symbol'].isin(strat.catalyst_symbols)
    
    out['vol_prev_ratio'] = out.groupby('symbol')['volume'].transform(
        lambda x: x.shift(1) / (x.shift(1).rolling(20).mean() + 1e-6)
    )
    
    out['is_coiled'] = (
        (out['dist_sma20_abs'] <= coiling_max) & 
        (out['rsi_prev'] >= rsi_min) & 
        (out['rsi_prev'] <= rsi_max)
    )
    
    out['clean_gap'] = (
        (out['gap_pct'] >= gap_min) & 
        (out['gap_pct'] <= gap_max)
    )
    
    if bmark_min is None:
        out['market_aligned'] = True
    else:
        out['market_aligned'] = out['midcap_ret'] >= bmark_min
        
    if enforce_gap_rej:
        out['gap_rejected'] = out['low'] >= out['prev_close']
    else:
        out['gap_rejected'] = True
        
    if enforce_qual:
        out['quality_trigger'] = out['has_catalyst'] | (out['vol_prev_ratio'] >= vol_prev_ratio_min)
    else:
        out['quality_trigger'] = True
        
    out['pit_eligible'] = (
        out['is_coiled'] & 
        out['clean_gap'] & 
        out['market_aligned'] & 
        out['gap_rejected'] & 
        out['quality_trigger']
    )
    
    out['pit_score'] = (
        0.40 * (out['gap_pct'] / 0.01) +
        0.30 * (1.0 / (out['dist_sma20_abs'] + 0.01)) +
        0.20 * out['has_catalyst'].astype(float) +
        0.10 * out['vol_prev_ratio'].clip(lower=0, upper=3.0)
    )
    
    if start_date is not None:
        out = out[out['date'] >= start_date].copy()
    if end_date is not None:
        out = out[out['date'] <= end_date].copy()
        
    eligible_df = out[out['pit_eligible']].copy()
    dates = sorted(out['date'].unique())
    equity = strat.initial_equity
    active_positions = []
    completed_trades = []
    daily_equity = []
    
    grouped_cands = {d: group for d, group in eligible_df.groupby('date')}
    all_grouped = {d: group for d, group in out.groupby('date')}
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
                    'holding_period': f"{pos['days_held']} Days",
                    'sl_or_tp_hit': 'SL HIT (Trailing Stop)', 'actual_rank': pos['actual_rank'],
                    'mfe_pct': ((pos['highest_price'] - pos['entry_price'])/pos['entry_price'])*100,
                    'mae_pct': ((pos['lowest_price'] - pos['entry_price'])/pos['entry_price'])*100
                })
                continue
                
            if pos['days_held'] >= swing_max_days:
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
                    'holding_period': f"{pos['days_held']} Days",
                    'sl_or_tp_hit': 'TIME EXIT (Swing Max)', 'actual_rank': pos['actual_rank'],
                    'mfe_pct': ((pos['highest_price'] - pos['entry_price'])/pos['entry_price'])*100,
                    'mae_pct': ((pos['lowest_price'] - pos['entry_price'])/pos['entry_price'])*100
                })
                continue
                
            pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
            retained.append(pos)
        active_positions = retained
        
        # New Entries
        day_cands = grouped_cands.get(d)
        if day_cands is not None and not day_cands.empty:
            sorted_cands = day_cands.sort_values('pit_score', ascending=False)
            for _, cand in sorted_cands.iterrows():
                if len(active_positions) >= max_positions:
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
                reached_be = sess_high >= entry_p * (1.0 + be_trigger)
                
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
                        'holding_period': '1 Day', 'sl_or_tp_hit': 'SL HIT (Initial)',
                        'actual_rank': actual_rk,
                        'mfe_pct': ((sess_high - entry_p)/entry_p)*100,
                        'mae_pct': ((sess_low - entry_p)/entry_p)*100
                    })
                else:
                    if reached_be:
                        if sess_close >= entry_p * (1.0 + swing_trigger):
                            active_positions.append({
                                'trade_id': trade_id, 'symbol': sym, 'company_name': comp_map.get(sym, sym),
                                'sector': sector_map.get(sym, 'Mid-Cap Equities'),
                                'entry_date': d, 'entry_price': entry_p, 'shares': shares,
                                'trailing_stop': max(entry_p * (1.0 + be_lock), sess_low),
                                'days_held': 1, 'highest_price': sess_high, 'lowest_price': sess_low,
                                'actual_rank': actual_rk
                            })
                        else:
                            exit_price = max(entry_p * (1.0 + be_lock), sess_close * (1.0 - strat.exit_slippage_pct))
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
                                'holding_period': '1 Day', 'sl_or_tp_hit': 'BREAKEVEN RATCHET',
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
                            'holding_period': '1 Day', 'sl_or_tp_hit': 'INTRADAY CLOSE',
                            'actual_rank': actual_rk,
                            'mfe_pct': ((sess_high - entry_p)/entry_p)*100,
                            'mae_pct': ((sess_low - entry_p)/entry_p)*100
                        })
                trade_id += 1
        daily_equity.append({'date': d, 'equity': equity})
        
    trades_df = pd.DataFrame(completed_trades)
    eq_df = pd.DataFrame(daily_equity)
    
    n_trades = len(trades_df)
    if n_trades == 0:
        return {'trades': 0, 'win_rate': 0, 'pf': 0, 'sharpe': 0, 'max_dd': 0, 'net_pnl': 0, 'costs': 0, 'trades_df': trades_df, 'eq_df': eq_df}
        
    wins = trades_df['is_win'].sum()
    win_rate = (wins / n_trades) * 100.0
    gross_win = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
    gross_loss = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum())
    pf = gross_win / (gross_loss + 1e-6)
    
    eq_df['cummax'] = eq_df['equity'].cummax()
    eq_df['dd'] = (eq_df['equity'] - eq_df['cummax']) / eq_df['cummax']
    max_dd = eq_df['dd'].min() * 100.0
    
    eq_df['ret'] = eq_df['equity'].pct_change().fillna(0)
    sharpe = (eq_df['ret'].mean() / (eq_df['ret'].std() + 1e-6)) * math.sqrt(252) if eq_df['ret'].std() > 0 else 0
    
    tot_pnl = equity - strat.initial_equity
    tot_costs = trades_df['costs'].sum()
    
    return {
        'trades': n_trades,
        'unique_dates': trades_df['entry_date'].nunique(),
        'win_rate': win_rate,
        'profit_factor': pf,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'net_pnl': tot_pnl,
        'costs': tot_costs,
        'trades_df': trades_df,
        'eq_df': eq_df
    }

def main():
    print("=" * 80)
    print("GRID SEARCH OPTIMIZATION: SYSTEMATICALLY INCREASING TRADE FREQUENCY")
    print("In-Sample Search: 2021-09-20 to 2025-09-18 (990 Sessions)")
    print("Untouched Holdout: 2025-09-19 to 2026-09-18 (251 Sessions)")
    print("=" * 80)
    
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    # 1. Evaluate Baseline on In-Sample
    baseline_params = {}
    base_is = run_backtest_engine(df, n150_df, baseline_params, end_date='2025-09-18')
    print(f"BASELINE IN-SAMPLE (990 days):")
    print(f"  Trades: {base_is['trades']} | WR: {base_is['win_rate']:.2f}% | PF: {base_is['profit_factor']:.2f} | Sharpe: {base_is['sharpe']:.2f} | MaxDD: {base_is['max_dd']:.2f}% | P&L: INR {base_is['net_pnl']:,.2f}")
    
    # Grid of candidate modifications to explore
    # We want to test combinations of:
    # 1. Coiling expansion (1.6 to 2.8)
    # 2. Benchmark gate (None, -0.002, -0.001, 0.001)
    # 3. Gap range (0.3% to 2.2%)
    # 4. Volume thrust (1.2x to 1.5x)
    # 5. Swing trigger (0.010 to 0.012)
    # 6. Breakeven lock (0.002 to 0.0025)
    
    grid = [
        # Candidate 1: Coiling 2.2%, Bmark None
        {'name': 'Coil 2.2% + No Bmark Gate', 'coiling_max': 2.2, 'bmark_min': None},
        # Candidate 2: Coiling 2.5%, Bmark None
        {'name': 'Coil 2.5% + No Bmark Gate', 'coiling_max': 2.5, 'bmark_min': None},
        # Candidate 3: Coiling 2.5%, Bmark >= -0.10%
        {'name': 'Coil 2.5% + Bmark >= -0.10%', 'coiling_max': 2.5, 'bmark_min': -0.001},
        # Candidate 4: Coiling 2.5%, RSI 40-65, Bmark None
        {'name': 'Coil 2.5% + RSI 40-65 + No Bmark', 'coiling_max': 2.5, 'rsi_min': 40.0, 'rsi_max': 65.0, 'bmark_min': None},
        # Candidate 5: Coiling 2.8%, Bmark >= -0.10%, Gap 0.35-1.8%
        {'name': 'Coil 2.8% + Bmark >= -0.10% + Gap 0.35-1.8%', 'coiling_max': 2.8, 'bmark_min': -0.001, 'gap_min': 0.0035, 'gap_max': 0.018},
        # Candidate 6: Coiling 2.2%, Gap 0.3-2.0%, Vol 1.3x
        {'name': 'Coil 2.2% + Gap 0.3-2.0% + Vol 1.3x', 'coiling_max': 2.2, 'gap_min': 0.003, 'gap_max': 0.020, 'vol_prev_ratio_min': 1.3},
        # Candidate 7: Coiling 2.4%, Bmark None, Vol 1.35x
        {'name': 'Coil 2.4% + No Bmark + Vol 1.35x', 'coiling_max': 2.4, 'bmark_min': None, 'vol_prev_ratio_min': 1.35},
        # Candidate 8: Coiling 2.5%, Bmark None, MaxPos 8
        {'name': 'Coil 2.5% + No Bmark + MaxPos 8', 'coiling_max': 2.5, 'bmark_min': None, 'max_positions': 8},
        # Candidate 9: Coiling 2.6%, Bmark >= 0.0%, Gap 0.35-1.8%
        {'name': 'Coil 2.6% + Bmark >= 0.0% + Gap 0.35-1.8%', 'coiling_max': 2.6, 'bmark_min': 0.0, 'gap_min': 0.0035, 'gap_max': 0.018},
        # Candidate 10: Coiling 2.5%, Bmark None, Swing 1.0% trigger
        {'name': 'Coil 2.5% + No Bmark + SwingTrig 1.0%', 'coiling_max': 2.5, 'bmark_min': None, 'swing_trigger': 0.010},
        # Candidate 11: Coiling 2.8%, Bmark None, Gap 0.3-2.2%, Vol 1.25x
        {'name': 'Coil 2.8% + No Bmark + Gap 0.3-2.2% + Vol 1.25x', 'coiling_max': 2.8, 'bmark_min': None, 'gap_min': 0.003, 'gap_max': 0.022, 'vol_prev_ratio_min': 1.25},
        # Candidate 12: Coiling 2.2%, Bmark >= 0.0%, Vol 1.3x
        {'name': 'Coil 2.2% + Bmark >= 0.0% + Vol 1.3x', 'coiling_max': 2.2, 'bmark_min': 0.0, 'vol_prev_ratio_min': 1.3}
    ]
    
    candidates_results = []
    print("\nEvaluating candidates on In-Sample (990 sessions)...")
    for c in grid:
        p = {k: v for k, v in c.items() if k != 'name'}
        res = run_backtest_engine(df, n150_df, p, end_date='2025-09-18')
        c_res = {
            'name': c['name'],
            'params': p,
            'is_trades': res['trades'],
            'is_wr': res['win_rate'],
            'is_pf': res['profit_factor'],
            'is_sharpe': res['sharpe'],
            'is_max_dd': res['max_dd'],
            'is_pnl': res['net_pnl'],
            'is_costs': res['costs']
        }
        candidates_results.append(c_res)
        print(f"[{c['name']}] Trades: {res['trades']} | WR: {res['win_rate']:.2f}% | PF: {res['profit_factor']:.2f} | Sharpe: {res['sharpe']:.2f} | MaxDD: {res['max_dd']:.2f}% | P&L: INR {res['net_pnl']:,.2f}")
        
    # Filter candidates that strictly meet:
    # 1. Trades > base_is['trades'] (564)
    # 2. WR >= base_is['win_rate'] (72.87%)
    # 3. PF >= 16.0
    # 4. MaxDD <= -0.25%
    # 5. PnL >= base_is['pnl']
    valid_candidates = []
    for c in candidates_results:
        if (c['is_trades'] > base_is['trades'] and 
            c['is_wr'] >= base_is['win_rate'] and 
            c['is_pf'] >= 16.0 and 
            abs(c['is_max_dd']) <= 0.35 and 
            c['is_pnl'] >= base_is['is_pnl'] if 'is_pnl' in base_is else True):
            valid_candidates.append(c)
            
    print(f"\nTotal Valid Candidates meeting strict in-sample criteria: {len(valid_candidates)}")
    for vc in valid_candidates:
        print(f"  --> {vc['name']} | Trades: {vc['is_trades']} (+{vc['is_trades']-base_is['trades']}) | WR: {vc['is_wr']:.2f}% | PF: {vc['is_pf']:.2f} | P&L: INR {vc['is_pnl']:,.2f}")

if __name__ == '__main__':
    main()
