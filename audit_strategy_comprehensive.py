import os
import sys
import math
import pandas as pd
import numpy as np
from scipy import stats

def run_comprehensive_audit():
    print("=" * 80)
    print("INDEPENDENT QUANTITATIVE AUDIT & ADVERSARIAL STRESS TEST")
    print("=" * 80)
    
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    # 1. Audit Survivorship Bias
    print("\n--- 1. AUDITING SURVIVORSHIP & SELECTION BIAS ---")
    print(f"Total symbols in static universe file: {len(n150_df)}")
    print(f"Dataset date range: {df['date'].min()} to {df['date'].max()}")
    print("Finding: The backtest uses a STATIC constituent list as of 2026 for the historical 2021-2026 period.")
    
    # Check if hyper-growth multi-baggers are in the dataset
    symbols_in_df = df['symbol'].unique()
    multibaggers = ['SUZLON', 'APARINDS', 'WAAREEENER', 'KAYNES', 'BSE']
    present_mb = [s for s in multibaggers if s in symbols_in_df]
    print(f"Hyper-growth midcap inclusions: {present_mb}")
    for s in present_mb:
        s_df = df[df['symbol'] == s]
        if not s_df.empty:
            p_start = s_df.iloc[0]['close']
            p_end = s_df.iloc[-1]['close']
            tot_gain = (p_end - p_start) / p_start * 100.0
            print(f"  {s}: 5-year price change: {tot_gain:+.1f}% (Start: {p_start:.2f}, End: {p_end:.2f})")
            
    # 2. Audit Look-ahead Bias & Data Leakage
    print("\n--- 2. AUDITING LOOK-AHEAD BIAS & DATA LEAKAGE ---")
    print("Testing mathematical leakage of rng_pos and vol_ratio into 09:30 AM execution...")
    corr_rng_intra = df['rng_pos'].corr(df['intraday_return'])
    corr_rng_daily = df['rng_pos'].corr(df['daily_return'])
    corr_vol_daily = df['vol_ratio'].corr(df['daily_return'])
    print(f"  Spearman/Pearson corr(rng_pos, intraday_return) : {corr_rng_intra:+.4f}")
    print(f"  Spearman/Pearson corr(rng_pos, daily_return)    : {corr_rng_daily:+.4f}")
    print(f"  Spearman/Pearson corr(vol_ratio, daily_return)  : {corr_vol_daily:+.4f}")
    
    # 3. Simulate Leak-Free Point-in-Time Model vs Leaked Model
    print("\n--- 3. SIMULATING LEAK-FREE POINT-IN-TIME MODEL VS REPORTED MODEL ---")
    dates = sorted(df['date'].unique())
    
    def simulate_engine(leak_free=False):
        equity = 10_000_000.0
        active_positions = []
        completed = []
        daily_equity = []
        
        grouped = {d: group for d, group in df.groupby('date')}
        
        for d in dates:
            day_df = grouped.get(d)
            if day_df is None or day_df.empty:
                daily_equity.append({'date': d, 'equity': equity})
                continue
                
            midcap_ret = day_df['midcap_ret'].iloc[0] if 'midcap_ret' in day_df.columns else 0.0
            
            # Manage Swings
            retained = []
            for pos in active_positions:
                if not pos['is_swing']:
                    retained.append(pos)
                    continue
                sym = pos['symbol']
                sym_row = day_df[day_df['symbol'] == sym]
                if sym_row.empty:
                    pos['days_held'] += 1
                    retained.append(pos)
                    continue
                row = sym_row.iloc[0]
                pos['days_held'] += 1
                curr_low = row['low']
                curr_close = row['close']
                if curr_low <= pos['trailing_stop']:
                    exit_p = pos['trailing_stop'] * 0.998
                    pnl = (exit_p - pos['entry_price']) * pos['shares']
                    charges = (pos['entry_price'] * pos['shares'] + exit_p * pos['shares']) * 0.0012 + 15.93
                    net_pnl = pnl - charges
                    equity += net_pnl
                    completed.append({
                        'date': pos['entry_date'], 'exit_date': d, 'symbol': sym,
                        'net_pnl': net_pnl, 'return_pct': (net_pnl / (pos['entry_price'] * pos['shares'])) * 100,
                        'is_win': net_pnl > 0, 'actual_rank': pos['actual_rank'], 'trade_type': 'SWING'
                    })
                    continue
                if pos['days_held'] >= 5:
                    exit_p = curr_close * 0.998
                    pnl = (exit_p - pos['entry_price']) * pos['shares']
                    charges = (pos['entry_price'] * pos['shares'] + exit_p * pos['shares']) * 0.0012 + 15.93
                    net_pnl = pnl - charges
                    equity += net_pnl
                    completed.append({
                        'date': pos['entry_date'], 'exit_date': d, 'symbol': sym,
                        'net_pnl': net_pnl, 'return_pct': (net_pnl / (pos['entry_price'] * pos['shares'])) * 100,
                        'is_win': net_pnl > 0, 'actual_rank': pos['actual_rank'], 'trade_type': 'SWING'
                    })
                    continue
                pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
                retained.append(pos)
            active_positions = retained
            
            # Headwind filter
            if midcap_ret < -0.005:
                daily_equity.append({'date': d, 'equity': equity})
                continue
                
            # Candidate screening
            passing = []
            for _, row in day_df.iterrows():
                dist_sma = abs(row['dist_sma20']) / 100.0 if pd.notnull(row['dist_sma20']) else 0.5
                rsi = row['rsi_prev'] if pd.notnull(row['rsi_prev']) else 50.0
                gap = row['gap_pct'] if pd.notnull(row['gap_pct']) else 0.0
                
                # Base Layer 1 coiling
                if not (dist_sma <= 0.03 and 35.0 <= rsi <= 65.0):
                    continue
                if not (0.002 <= gap <= 0.025):
                    continue
                    
                if leak_free:
                    # In LEAK-FREE mode: We DO NOT use end-of-day rng_pos or full-day volume!
                    # We only use prior day volume ratio (vol_5d / vol_20d) or purely gap & coiling!
                    # Passing candidate based on strictly known features:
                    passing.append(row)
                else:
                    # Leaked mode (Reported Strategy): uses day's full volume & full day's close in rng_pos
                    vol = row['vol_ratio'] if pd.notnull(row['vol_ratio']) else 1.0
                    rng = row['rng_pos'] if pd.notnull(row['rng_pos']) else 0.5
                    if vol >= 1.60 and not (vol >= 1.5 and rng <= 0.40):
                        passing.append(row)
                        
            if not passing:
                daily_equity.append({'date': d, 'equity': equity})
                continue
                
            pass_df = pd.DataFrame(passing)
            
            if leak_free:
                # Strictly point-in-time ranking at 09:15 AM:
                # Rank by gap momentum + tightness of coiling + historical RSI
                g_norm = (pass_df['gap_pct'] - pass_df['gap_pct'].mean()) / (pass_df['gap_pct'].std() + 1e-6)
                c_norm = ((1.0 / (pass_df['dist_sma20'].abs() + 0.005)) - (1.0 / (pass_df['dist_sma20'].abs() + 0.005)).mean()) / ((1.0 / (pass_df['dist_sma20'].abs() + 0.005)).std() + 1e-6)
                r_norm = (pass_df['rsi_prev'] - pass_df['rsi_prev'].mean()) / (pass_df['rsi_prev'].std() + 1e-6)
                pass_df['score'] = 0.50 * g_norm + 0.30 * c_norm + 0.20 * r_norm
            else:
                v_norm = (pass_df['vol_ratio'] - pass_df['vol_ratio'].mean()) / (pass_df['vol_ratio'].std() + 1e-6)
                r_norm = (pass_df['rng_pos'] - pass_df['rng_pos'].mean()) / (pass_df['rng_pos'].std() + 1e-6)
                g_norm = (pass_df['gap_pct'] - pass_df['gap_pct'].mean()) / (pass_df['gap_pct'].std() + 1e-6)
                c_norm = ((1.0 / (pass_df['dist_sma20'].abs() + 0.005)) - (1.0 / (pass_df['dist_sma20'].abs() + 0.005)).mean()) / ((1.0 / (pass_df['dist_sma20'].abs() + 0.005)).std() + 1e-6)
                pass_df['score'] = 0.45 * v_norm + 0.35 * r_norm + 0.10 * g_norm + 0.10 * c_norm
                
            pass_df = pass_df.sort_values('score', ascending=False)
            
            for _, cand in pass_df.iterrows():
                if len(active_positions) >= 5:
                    break
                sym = cand['symbol']
                if any(p['symbol'] == sym for p in active_positions):
                    continue
                open_p = cand['open']
                entry_p = open_p * 1.003
                sess_low = cand['low']
                sess_high = cand['high']
                sess_close = cand['close']
                actual_rk = cand['rank']
                
                pos_cap = min(equity * 0.10, 2_000_000.0)
                shares = int(pos_cap / entry_p)
                if shares <= 0:
                    continue
                buy_val = entry_p * shares
                initial_sl = entry_p * 0.98
                
                if sess_low <= initial_sl:
                    exit_p = initial_sl * 0.998
                    pnl = (exit_p - entry_p) * shares
                    charges = (buy_val + exit_p * shares) * 0.0003 + (exit_p * shares * 0.00025)
                    net_pnl = pnl - charges
                    equity += net_pnl
                    completed.append({
                        'date': d, 'exit_date': d, 'symbol': sym,
                        'net_pnl': net_pnl, 'return_pct': (net_pnl / buy_val) * 100,
                        'is_win': net_pnl > 0, 'actual_rank': actual_rk, 'trade_type': 'INTRADAY'
                    })
                else:
                    # In leak-free mode, swing transition requires that at 15:15 close, stock held upper range
                    # That is valid at 15:15 close!
                    cand_rng_at_close = (sess_close - sess_low) / (sess_high - sess_low + 1e-6)
                    is_swing = (cand_rng_at_close >= 0.70)
                    if is_swing:
                        active_positions.append({
                            'symbol': sym, 'entry_date': d, 'entry_price': entry_p, 'shares': shares,
                            'allocated_capital': buy_val, 'trailing_stop': sess_low, 'days_held': 1,
                            'is_swing': True, 'actual_rank': actual_rk
                        })
                    else:
                        exit_p = sess_close * 0.998
                        pnl = (exit_p - entry_p) * shares
                        charges = (buy_val + exit_p * shares) * 0.0003 + (exit_p * shares * 0.00025)
                        net_pnl = pnl - charges
                        equity += net_pnl
                        completed.append({
                            'date': d, 'exit_date': d, 'symbol': sym,
                            'net_pnl': net_pnl, 'return_pct': (net_pnl / buy_val) * 100,
                            'is_win': net_pnl > 0, 'actual_rank': actual_rk, 'trade_type': 'INTRADAY'
                        })
            daily_equity.append({'date': d, 'equity': equity})
            
        t_df = pd.DataFrame(completed)
        eq_df = pd.DataFrame(daily_equity)
        
        eq_df['ret'] = eq_df['equity'].pct_change().fillna(0.0)
        sharpe = ((eq_df['ret'].mean() - 0.06/252) / (eq_df['ret'].std() + 1e-9)) * math.sqrt(252)
        eq_df['peak'] = eq_df['equity'].cummax()
        maxdd = ((eq_df['equity'] - eq_df['peak']) / eq_df['peak']).min() * 100.0
        
        total = len(t_df)
        wins = t_df['is_win'].sum()
        wr = (wins / total) * 100 if total > 0 else 0.0
        gw = t_df[t_df['net_pnl'] > 0]['net_pnl'].sum()
        gl = abs(t_df[t_df['net_pnl'] < 0]['net_pnl'].sum())
        pf = (gw / gl) if gl > 0 else 99.9
        
        t1 = (t_df['actual_rank'] == 1).sum()
        t5 = (t_df['actual_rank'] <= 5).sum()
        t10 = (t_df['actual_rank'] <= 10).sum()
        t20 = (t_df['actual_rank'] <= 20).sum()
        
        return {
            'total_trades': total, 'wins': wins, 'losses': total - wins, 'win_rate': wr,
            'pf': pf, 'sharpe': sharpe, 'maxdd': maxdd, 'net_pnl': equity - 10_000_000.0,
            'top1': t1, 'top5': t5, 'top10': t10, 'top20': t20,
            't_df': t_df, 'eq_df': eq_df
        }
        
    print("Running Model 1 (Reported Backtest with Leaked Intraday Variables)...")
    res_leaked = simulate_engine(leak_free=False)
    print("Running Model 2 (Strictly Point-in-Time Leak-Free Model at 09:15 AM)...")
    res_clean = simulate_engine(leak_free=True)
    
    print("\n================================================================================")
    print("CRITICAL FINDINGS: LEAKED REPORTED BACKTEST VS STRICTLY POINT-IN-TIME MODEL")
    print("================================================================================")
    print(f"Metric                        | Reported Backtest (Leaked) | Point-in-Time (Leak-Free)")
    print(f"----------------------------- | -------------------------- | -------------------------")
    print(f"Total Trades                  | {res_leaked['total_trades']:>26} | {res_clean['total_trades']:>25}")
    print(f"Win Rate                      | {res_leaked['win_rate']:>25.2f}% | {res_clean['win_rate']:>24.2f}%")
    print(f"Profit Factor                 | {res_leaked['pf']:>26.2f} | {res_clean['pf']:>25.2f}")
    print(f"Sharpe Ratio                  | {res_leaked['sharpe']:>26.2f} | {res_clean['sharpe']:>25.2f}")
    print(f"Maximum Drawdown              | {res_leaked['maxdd']:>25.2f}% | {res_clean['maxdd']:>24.2f}%")
    print(f"Total Net P&L (INR)           | INR {res_leaked['net_pnl']:>22,.2f} | INR {res_clean['net_pnl']:>21,.2f}")
    print(f"Exact #1 Universe Hits        | {res_leaked['top1']:>26} | {res_clean['top1']:>25}")
    print(f"Top 5 Universe Hits           | {res_leaked['top5']:>26} | {res_clean['top5']:>25}")
    print(f"Top 20 Universe Hits          | {res_leaked['top20']:>26} | {res_clean['top20']:>25}")
    
    return res_leaked, res_clean

if __name__ == '__main__':
    run_comprehensive_audit()
