import os
import sys
import math
import numpy as np
import pandas as pd
from strategy.point_in_time_strategy import PointInTimeStrategy

def run_diagnostic():
    print("=" * 80)
    print("RUNNING TRADE FREQUENCY & TOP-GAINER OPPORTUNITY AUDIT")
    print("=" * 80)
    
    df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    comp_map = dict(zip(n150_df['Symbol'], n150_df['Company Name']))
    
    strat = PointInTimeStrategy(initial_equity=10_000_000.0)
    feat_df = strat.compute_pit_features(df)
    
    dates = sorted(feat_df['date'].unique())
    total_days = len(dates)
    print(f"Total Trading Sessions: {total_days}")
    
    # 1. Inspect Candidate Eligibility Across All Days
    days_with_pit_cands = feat_df[feat_df['pit_eligible']]['date'].nunique()
    total_pit_cands = feat_df['pit_eligible'].sum()
    print(f"Days with at least 1 PIT-eligible candidate: {days_with_pit_cands} / {total_days} ({days_with_pit_cands/total_days*100:.2f}%)")
    print(f"Total PIT-eligible candidate stock-days: {total_pit_cands}")
    
    # 2. Daily Filter Failure Breakdown (Why do days have 0 candidates?)
    all_grouped = {d: group for d, group in feat_df.groupby('date')}
    
    zero_cand_days = 0
    reasons_zero_cand_days = {
        'benchmark_negative': 0, # Benchmark opened down (< +0.10%)
        'no_coiled_stocks': 0,   # No stocks met 20-DMA coiling & RSI
        'no_clean_gap': 0,       # No stocks opened with gap 0.4% - 1.6%
        'no_gap_rejected': 0,    # All gappers failed low >= prev_close
        'no_vol_thrust': 0,      # All gappers failed volume/catalyst trigger
        'combination_fail': 0    # Individual stocks passed some but none passed all
    }
    
    # Detailed count of stocks passing each stage on zero-candidate days
    zero_days_stats = []
    
    for d in dates:
        day_df = all_grouped[d]
        cands = day_df[day_df['pit_eligible']]
        if len(cands) == 0:
            zero_cand_days += 1
            bmark_ret = day_df['midcap_ret'].iloc[0]
            mkt_ok = bmark_ret >= strat.benchmark_headwind_min
            coil_cnt = day_df['is_coiled'].sum()
            gap_cnt = day_df['clean_gap'].sum()
            gap_rej_cnt = (day_df['clean_gap'] & day_df['gap_rejected']).sum()
            qual_cnt = (day_df['clean_gap'] & day_df['gap_rejected'] & day_df['quality_trigger']).sum()
            
            zero_days_stats.append({
                'date': d, 'bmark_ret': bmark_ret, 'mkt_ok': mkt_ok,
                'coil_cnt': coil_cnt, 'gap_cnt': gap_cnt,
                'gap_rej_cnt': gap_rej_cnt, 'qual_cnt': qual_cnt
            })
            
            if not mkt_ok:
                reasons_zero_cand_days['benchmark_negative'] += 1
            elif coil_cnt == 0:
                reasons_zero_cand_days['no_coiled_stocks'] += 1
            elif gap_cnt == 0:
                reasons_zero_cand_days['no_clean_gap'] += 1
            elif gap_rej_cnt == 0:
                reasons_zero_cand_days['no_gap_rejected'] += 1
            elif qual_cnt == 0:
                reasons_zero_cand_days['no_vol_thrust'] += 1
            else:
                reasons_zero_cand_days['combination_fail'] += 1
                
    print("\n--- ZERO-CANDIDATE DAY ROOT CAUSES ---")
    print(f"Total Zero-Candidate Days: {zero_cand_days} / {total_days} ({zero_cand_days/total_days*100:.2f}%)")
    for r, cnt in reasons_zero_cand_days.items():
        print(f"  {r}: {cnt} days ({cnt/zero_cand_days*100:.1f}%)")
        
    # 3. Filter Pass Rates across ALL 169,920 Stock-Days
    print("\n--- FILTER PASS RATES ACROSS ALL 169,920 STOCK-DAYS ---")
    print(f"1. Benchmark Aligned (midcap_ret >= +0.10%): {feat_df['market_aligned'].mean()*100:.2f}% ({feat_df['market_aligned'].sum():,} stock-days)")
    print(f"2. Coiling Gate (dist_sma20 <= 1.6% & RSI 45-60): {feat_df['is_coiled'].mean()*100:.2f}% ({feat_df['is_coiled'].sum():,} stock-days)")
    print(f"3. Clean Gap Gate (+0.4% <= gap <= +1.6%): {feat_df['clean_gap'].mean()*100:.2f}% ({feat_df['clean_gap'].sum():,} stock-days)")
    print(f"4. Gap-Fill Rejection (low >= prev_close): {feat_df['gap_rejected'].mean()*100:.2f}% ({feat_df['gap_rejected'].sum():,} stock-days)")
    print(f"5. Quality Trigger (Catalyst or Vol Thrust >= 1.5x): {feat_df['quality_trigger'].mean()*100:.2f}% ({feat_df['quality_trigger'].sum():,} stock-days)")
    print(f"6. Joint Pass Rate (All 5 Gates Met): {feat_df['pit_eligible'].mean()*100:.4f}% ({feat_df['pit_eligible'].sum():,} stock-days)")
    
    # 4. Analysis of Actual Universe Top Gainers (Rank #1, Top 5, Top 10)
    print("\n--- ANALYSIS OF ACTUAL UNIVERSE TOP GAINERS ---")
    rank1_df = feat_df[feat_df['rank'] == 1].copy()
    print(f"Total Rank #1 Stock-Days: {len(rank1_df)}")
    
    r1_bmark = rank1_df['market_aligned'].sum()
    r1_coil = rank1_df['is_coiled'].sum()
    r1_gap = rank1_df['clean_gap'].sum()
    r1_gap_rej = rank1_df['gap_rejected'].sum()
    r1_qual = rank1_df['quality_trigger'].sum()
    r1_passed_all = rank1_df['pit_eligible'].sum()
    
    print(f"Rank #1 Gainers Passing Benchmark Filter: {r1_bmark} / {len(rank1_df)} ({r1_bmark/len(rank1_df)*100:.1f}%)")
    print(f"Rank #1 Gainers Passing Coiling Filter: {r1_coil} / {len(rank1_df)} ({r1_coil/len(rank1_df)*100:.1f}%)")
    print(f"Rank #1 Gainers Passing Clean Gap Filter: {r1_gap} / {len(rank1_df)} ({r1_gap/len(rank1_df)*100:.1f}%)")
    print(f"Rank #1 Gainers Passing Gap-Fill Rejection: {r1_gap_rej} / {len(rank1_df)} ({r1_gap_rej/len(rank1_df)*100:.1f}%)")
    print(f"Rank #1 Gainers Passing Quality/Catalyst Trigger: {r1_qual} / {len(rank1_df)} ({r1_qual/len(rank1_df)*100:.1f}%)")
    print(f"Rank #1 Gainers Passing ALL 5 Filters: {r1_passed_all} / {len(rank1_df)} ({r1_passed_all/len(rank1_df)*100:.1f}%)")
    
    print(f"Rank 1 Mean Gap: {rank1_df['gap_pct'].mean()*100:.2f}%, Median Gap: {rank1_df['gap_pct'].median()*100:.2f}%")
    print(f"Rank 1 with Gap < 0.4%: {(rank1_df['gap_pct'] < 0.004).sum()} ({(rank1_df['gap_pct'] < 0.004).mean()*100:.1f}%)")
    print(f"Rank 1 with Gap 0.4% - 1.6%: {((rank1_df['gap_pct'] >= 0.004) & (rank1_df['gap_pct'] <= 0.016)).sum()} ({((rank1_df['gap_pct'] >= 0.004) & (rank1_df['gap_pct'] <= 0.016)).mean()*100:.1f}%)")
    print(f"Rank 1 with Gap > 1.6%: {(rank1_df['gap_pct'] > 0.016).sum()} ({(rank1_df['gap_pct'] > 0.016).mean()*100:.1f}%)")
    print(f"Rank 1 with Low < Prev_Close (dipped below prev close): {(rank1_df['low'] < rank1_df['prev_close']).sum()} ({(rank1_df['low'] < rank1_df['prev_close']).mean()*100:.1f}%)")
    print(f"Rank 1 with dist_sma20 > 1.6% (already extended): {(rank1_df['dist_sma20_abs'] > 1.6).sum()} ({(rank1_df['dist_sma20_abs'] > 1.6).mean()*100:.1f}%)")
    
    # 5. Counterfactual Simulation: What happens if we trade the REJECTED Rank #1 Gainers?
    rejected_r1 = rank1_df[~rank1_df['pit_eligible']].copy()
    print(f"\n--- COUNTERFACTUAL SIMULATION: TRADING REJECTED RANK #1 GAINERS ({len(rejected_r1)} STOCKS) ---")
    
    sim_results = []
    for _, row in rejected_r1.iterrows():
        open_p = row['open']
        entry_p = open_p * 1.002
        sess_low = row['low']
        sess_high = row['high']
        sess_close = row['close']
        initial_sl = max(row['prev_close'] * 0.998, entry_p * (1.0 - strat.initial_stop_loss_pct))
        
        if sess_low <= initial_sl:
            exit_p = initial_sl * 0.998
            is_win = False
            sl_hit = True
            ret_pct = ((exit_p - entry_p) / entry_p) * 100.0 - 0.40
        else:
            sl_hit = False
            reached_be = sess_high >= entry_p * 1.010
            if reached_be:
                if sess_close >= entry_p * 1.012:
                    exit_p = sess_close * 0.998
                else:
                    exit_p = max(entry_p * 1.002, sess_close * 0.998)
            else:
                exit_p = sess_close * 0.998
            ret_pct = ((exit_p - entry_p) / entry_p) * 100.0 - 0.40
            is_win = ret_pct > 0
            
        sim_results.append({
            'symbol': row['symbol'], 'date': row['date'], 'entry_price': entry_p,
            'exit_price': exit_p, 'return_pct': ret_pct, 'is_win': is_win,
            'sl_hit': sl_hit, 'sess_low': sess_low, 'initial_sl': initial_sl,
            'gap_pct': row['gap_pct'], 'dist_sma20': row['dist_sma20'],
            'close': sess_close, 'open': open_p
        })
        
    sim_df = pd.DataFrame(sim_results)
    sim_wins = sim_df['is_win'].sum()
    sim_losses = len(sim_df) - sim_wins
    sim_wr = (sim_wins / len(sim_df)) * 100.0
    sim_sl_hits = sim_df['sl_hit'].sum()
    gross_gains = sim_df[sim_df['return_pct'] > 0]['return_pct'].sum()
    gross_losses = abs(sim_df[sim_df['return_pct'] < 0]['return_pct'].sum())
    sim_pf = gross_gains / (gross_losses + 1e-6)
    
    print(f"Rejected Rank #1 Gainers Count: {len(sim_df)}")
    print(f"Hypothetical Wins: {sim_wins} ({sim_wr:.2f}%)")
    print(f"Hypothetical Losses: {sim_losses} ({100-sim_wr:.2f}%)")
    print(f"Initial Stop Loss Triggered: {sim_sl_hits} ({sim_sl_hits/len(sim_df)*100:.1f}%)")
    print(f"Average Trade Return: {sim_df['return_pct'].mean():.2f}%")
    print(f"Hypothetical Profit Factor: {sim_pf:.2f}")
    
    # 6. Top 5 Gainers Analysis
    top5_df = feat_df[feat_df['rank'] <= 5].copy()
    top5_eligible = top5_df['pit_eligible'].sum()
    print(f"\n--- TOP 5 GAINERS ELIGIBILITY ---")
    print(f"Total Top 5 Gainer Stock-Days: {len(top5_df)}")
    print(f"Top 5 Gainers Passing All Filters: {top5_eligible} / {len(top5_df)} ({top5_eligible/len(top5_df)*100:.2f}%)")
    
    # 7. Actual Traded Portfolio Opportunities vs Rejections
    trades = pd.read_pickle(r'e:\stock_predictor\stock_predictor\point_in_time_trades_5year_detailed.pkl')
    print(f"\n--- ACTUAL TRADED OPPORTUNITIES BREAKDOWN ---")
    print(f"Total Completed Trades: {len(trades)}")
    print(f"Unique Entry Dates: {trades['entry_date'].nunique()} / {total_days}")
    print(f"Traded Opportunities that were Universe Rank 1: {(trades['actual_rank'] == 1).sum()}")
    print(f"Traded Opportunities that were Universe Top 5: {(trades['actual_rank'] <= 5).sum()}")
    print(f"Traded Opportunities that were Universe Top 10: {(trades['actual_rank'] <= 10).sum()}")
    print(f"Traded Opportunities that were Universe Top 20: {(trades['actual_rank'] <= 20).sum()}")

if __name__ == '__main__':
    run_diagnostic()
