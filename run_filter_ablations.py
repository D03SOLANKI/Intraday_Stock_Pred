import os
import sys
import math
import numpy as np
import pandas as pd
from strategy.point_in_time_strategy import PointInTimeStrategy

def run_simulation(df, n150_df, params, label):
    comp_map = dict(zip(n150_df['Symbol'], n150_df['Company Name']))
    sector_map = dict(zip(n150_df['Symbol'], n150_df['Sector'])) if 'Sector' in n150_df.columns else {}
    
    strat = PointInTimeStrategy(initial_equity=10_000_000.0)
    
    # Overwrite strategy parameters based on params dict
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
                    'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                    'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                    'capital': buy_val, 'actual_rank': pos['actual_rank']
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
                    'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                    'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                    'capital': buy_val, 'actual_rank': pos['actual_rank']
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
                        'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                        'is_win': False, 'costs': costs['total_charges'],
                        'capital': buy_val, 'actual_rank': actual_rk
                    })
                else:
                    if reached_be:
                        if sess_close >= entry_p * (1.0 + strat.swing_trigger_pct):
                            active_positions.append({
                                'trade_id': trade_id, 'symbol': sym,
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
                                'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                                'is_win': True, 'costs': costs['total_charges'],
                                'capital': buy_val, 'actual_rank': actual_rk
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
                            'symbol': sym, 'net_pnl': net_pnl, 'return_pct': (net_pnl/buy_val)*100,
                            'is_win': net_pnl > 0, 'costs': costs['total_charges'],
                            'capital': buy_val, 'actual_rank': actual_rk
                        })
                trade_id += 1
        daily_equity.append({'date': d, 'equity': equity})
        
    # Analyze Results
    trades_df = pd.DataFrame(completed_trades)
    eq_df = pd.DataFrame(daily_equity)
    
    n_trades = len(trades_df)
    if n_trades == 0:
        return {'label': label, 'trades': 0, 'win_rate': 0, 'pf': 0, 'sharpe': 0, 'max_dd': 0, 'net_pnl': 0, 'costs': 0}
        
    wins = trades_df['is_win'].sum()
    win_rate = (wins / n_trades) * 100.0
    gross_win = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
    gross_loss = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum())
    pf = gross_win / (gross_loss + 1e-6)
    
    eq_df['cummax'] = eq_df['equity'].cummax()
    eq_df['dd'] = (eq_df['equity'] - eq_df['cummax']) / eq_df['cummax']
    max_dd = eq_df['dd'].min() * 100.0
    
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
    trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])
    
    # Holdout (Sep 19, 2025 onwards)
    holdout_trades = trades_df[trades_df['entry_date'] >= '2025-09-19']
    if len(holdout_trades) > 0:
        ho_wr = (holdout_trades['is_win'].sum() / len(holdout_trades)) * 100.0
        ho_win = holdout_trades[holdout_trades['net_pnl'] > 0]['net_pnl'].sum()
        ho_loss = abs(holdout_trades[holdout_trades['net_pnl'] < 0]['net_pnl'].sum())
        ho_pf = ho_win / (ho_loss + 1e-6)
    else:
        ho_wr, ho_pf = 0.0, 0.0
        
    # Sharpe
    eq_df['ret'] = eq_df['equity'].pct_change().fillna(0)
    sharpe = (eq_df['ret'].mean() / (eq_df['ret'].std() + 1e-6)) * math.sqrt(252) if eq_df['ret'].std() > 0 else 0
    
    tot_pnl = equity - strat.initial_equity
    tot_costs = trades_df['costs'].sum()
    
    # Top gainer capture
    r1_traded = (trades_df['actual_rank'] == 1).sum()
    top5_traded = (trades_df['actual_rank'] <= 5).sum()
    unique_dates = trades_df['entry_date'].nunique()
    
    return {
        'label': label,
        'trades': n_trades,
        'unique_dates': unique_dates,
        'win_rate': win_rate,
        'profit_factor': pf,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'net_pnl': tot_pnl,
        'costs': tot_costs,
        'ho_trades': len(holdout_trades),
        'ho_win_rate': ho_wr,
        'ho_pf': ho_pf,
        'r1_traded': r1_traded,
        'top5_traded': top5_traded
    }

def main():
    print("Loading data for ablation study...")
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    ablations = [
        ({'label': '1. Baseline (Current Strategy)'}, {}),
        ({'label': '2. Remove Gap-Fill Rejection (Allow all gaps)'}, {'enforce_gap_rej': False}),
        ({'label': '3. Widen Gap Range (0.0% to 3.0%)'}, {'gap_min': 0.000, 'gap_max': 0.030}),
        ({'label': '4. Remove Benchmark Gate (Trade in all markets)'}, {'bmark_min': None}),
        ({'label': '5. Relax Benchmark Gate (Allow midcap_ret >= -0.30%)'}, {'bmark_min': -0.003}),
        ({'label': '6. Relax Volume Thrust (vol_prev_ratio >= 1.0x)'}, {'vol_prev_ratio_min': 1.0}),
        ({'label': '7. Relax Coiling (dist_sma20 <= 3.0%, RSI 35-70)'}, {'coiling_max': 3.0, 'rsi_min': 35.0, 'rsi_max': 70.0}),
        ({'label': '8. Increase Max Positions (5 -> 10)'}, {'max_positions': 10}),
        ({'label': '9. Combined Moderate Relaxation (Gap 0.2-2.5%, Coiling <=2.5%, Bmark >=-0.2%)'}, {
            'gap_min': 0.002, 'gap_max': 0.025, 'coiling_max': 2.5, 'bmark_min': -0.002, 'vol_prev_ratio_min': 1.2
        })
    ]
    
    results = []
    for info, p in ablations:
        lbl = info['label']
        print(f"Running simulation: {lbl}...")
        res = run_simulation(df, n150_df, p, lbl)
        results.append(res)
        print(f"  --> Trades: {res['trades']} | WR: {res['win_rate']:.2f}% | PF: {res['profit_factor']:.2f} | Sharpe: {res['sharpe']:.2f} | MaxDD: {res['max_dd']:.2f}% | P&L: INR {res['net_pnl']:,.2f} | Holdout WR: {res['ho_win_rate']:.2f}%")
        
    res_df = pd.DataFrame(results)
    res_df.to_csv(r'e:\stock_predictor\stock_predictor\ablation_results.csv', index=False)
    print("\nAblation study complete! Saved to ablation_results.csv")

if __name__ == '__main__':
    main()
