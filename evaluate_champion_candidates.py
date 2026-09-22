import os
import sys
import math
import numpy as np
import pandas as pd
from optimize_trade_frequency import run_backtest_engine

def evaluate():
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    candidates = [
        ('Baseline (Current Fixed Strategy)', {}),
        ('Candidate A (Coiling 2.5% + No Bmark Gate)', {'coiling_max': 2.5, 'bmark_min': None}),
        ('Candidate B (Coiling 2.5% + No Bmark + MaxPos 8)', {'coiling_max': 2.5, 'bmark_min': None, 'max_positions': 8}),
        ('Candidate C (Coiling 2.5% + RSI 40-65 + No Bmark)', {'coiling_max': 2.5, 'rsi_min': 40.0, 'rsi_max': 65.0, 'bmark_min': None}),
        ('Candidate D (Coiling 2.4% + Bmark >= -0.10% + Vol 1.35x)', {'coiling_max': 2.4, 'bmark_min': -0.001, 'vol_prev_ratio_min': 1.35}),
        ('Candidate E (Coiling 2.6% + No Bmark + Gap 0.35-1.8%)', {'coiling_max': 2.6, 'bmark_min': None, 'gap_min': 0.0035, 'gap_max': 0.018}),
    ]
    
    full_results = []
    
    print("=" * 100)
    print(f"{'Candidate Name':<45} | {'Trades':<6} | {'WR (%)':<6} | {'PF':<6} | {'Sharpe':<6} | {'MaxDD':<7} | {'Net P&L (INR)':<15} | {'HO Trades':<9} | {'HO WR (%)':<9} | {'HO PF':<6}")
    print("=" * 100)
    
    for name, p in candidates:
        res_full = run_backtest_engine(df, n150_df, p)
        tdf = res_full['trades_df']
        tdf['entry_date'] = pd.to_datetime(tdf['entry_date'])
        
        ho_df = tdf[tdf['entry_date'] >= '2025-09-19']
        ho_trades = len(ho_df)
        if ho_trades > 0:
            ho_wr = (ho_df['is_win'].sum() / ho_trades) * 100.0
            ho_win = ho_df[ho_df['net_pnl'] > 0]['net_pnl'].sum()
            ho_loss = abs(ho_df[ho_df['net_pnl'] < 0]['net_pnl'].sum())
            ho_pf = ho_win / (ho_loss + 1e-6)
            ho_pnl = ho_df['net_pnl'].sum()
        else:
            ho_wr, ho_pf, ho_pnl = 0, 0, 0
            
        print(f"{name:<45} | {res_full['trades']:<6} | {res_full['win_rate']:<6.2f} | {res_full['profit_factor']:<6.2f} | {res_full['sharpe']:<6.2f} | {res_full['max_dd']:<7.2f} | INR {res_full['net_pnl']:<10,.0f} | {ho_trades:<9} | {ho_wr:<9.2f} | {ho_pf:<6.2f}")
        
        full_results.append({
            'name': name, 'params': p, 'trades': res_full['trades'],
            'win_rate': res_full['win_rate'], 'pf': res_full['profit_factor'],
            'sharpe': res_full['sharpe'], 'max_dd': res_full['max_dd'],
            'net_pnl': res_full['net_pnl'], 'costs': res_full['costs'],
            'ho_trades': ho_trades, 'ho_wr': ho_wr, 'ho_pf': ho_pf,
            'ho_pnl': ho_pnl, 'trades_df': tdf
        })
        
    return full_results

if __name__ == '__main__':
    evaluate()
