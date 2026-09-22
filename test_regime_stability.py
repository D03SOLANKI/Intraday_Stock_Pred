import os
import sys
import math
import numpy as np
import pandas as pd
from optimize_trade_frequency import run_backtest_engine

def analyze_regimes():
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    cand_b_params = {'coiling_max': 2.5, 'bmark_min': None, 'max_positions': 8}
    cand_e_params = {'coiling_max': 2.6, 'bmark_min': None, 'gap_min': 0.0035, 'gap_max': 0.018}
    base_params = {}
    
    print("Running multi-regime audit for Baseline, Candidate B, and Candidate E...")
    res_base = run_backtest_engine(df, n150_df, base_params)
    res_b = run_backtest_engine(df, n150_df, cand_b_params)
    res_e = run_backtest_engine(df, n150_df, cand_e_params)
    
    for name, res in [('Baseline', res_base), ('Candidate B (Champion)', res_b), ('Candidate E (Aggressive)', res_e)]:
        tdf = res['trades_df'].copy()
        tdf['entry_date'] = pd.to_datetime(tdf['entry_date'])
        
        # Yearly Breakdown
        tdf['year'] = tdf['entry_date'].dt.year
        print(f"\n{'='*20} {name.upper()} YEARLY BREAKDOWN {'='*20}")
        print(f"{'Year':<6} | {'Trades':<8} | {'Win Rate (%)':<14} | {'PF':<8} | {'Net P&L (INR)':<15}")
        print("-" * 60)
        for yr, group in tdf.groupby('year'):
            wr = (group['is_win'].sum() / len(group)) * 100.0
            gw = group[group['net_pnl'] > 0]['net_pnl'].sum()
            gl = abs(group[group['net_pnl'] < 0]['net_pnl'].sum())
            pf = gw / (gl + 1e-6)
            pnl = group['net_pnl'].sum()
            print(f"{yr:<6} | {len(group):<8} | {wr:<14.2f} | {pf:<8.2f} | INR {pnl:<12,.0f}")
            
    # Save the detailed trade logs for Candidate B
    res_b['trades_df'].to_csv(r'e:\stock_predictor\stock_predictor\improved_strategy_candidate_b_trades.csv', index=False)
    res_b['trades_df'].to_pickle(r'e:\stock_predictor\stock_predictor\improved_strategy_candidate_b_trades.pkl')
    print("\nSaved Candidate B detailed trade log to improved_strategy_candidate_b_trades.csv and .pkl")

if __name__ == '__main__':
    analyze_regimes()
