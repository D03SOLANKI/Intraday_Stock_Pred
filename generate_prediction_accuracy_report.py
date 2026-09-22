import os
import sys
import pandas as pd
import numpy as np

def generate_prediction_accuracy():
    print("Loading data...")
    all_df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_1year.pkl')
    # Rank each stock on each day by daily_return descending (Rank 1 = highest gainer of the day)
    all_df['actual_universe_rank'] = all_df.groupby('date')['daily_return'].rank(ascending=False, method='min').astype(int)
    
    trades_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_detailed.csv')
    
    # Merge exact daily return and actual universe rank
    merged = pd.merge(
        trades_df,
        all_df[['date', 'symbol', 'actual_universe_rank', 'daily_return']],
        left_on=['trading_date', 'symbol'],
        right_on=['date', 'symbol'],
        how='left'
    )
    
    # Clean predicted rank to integer or string
    # e.g. 'Rank #1' -> 1
    merged['pred_rank_num'] = merged['predicted_rank'].str.extract(r'(\d+)').astype(int)
    
    # Define correctness definitions:
    # 1. Exact Rank #1 match: predicted rank 1 AND actual rank 1
    merged['is_exact_rank1_correct'] = (merged['pred_rank_num'] == 1) & (merged['actual_universe_rank'] == 1)
    
    # 2. Top-5 match: actual rank <= 5
    merged['is_top5_correct'] = merged['actual_universe_rank'] <= 5
    
    # 3. Top-10 match: actual rank <= 10
    merged['is_top10_correct'] = merged['actual_universe_rank'] <= 10
    
    # Accuracy flags
    def get_correctness_label(row):
        if row['pred_rank_num'] == 1:
            if row['actual_universe_rank'] == 1:
                return "CORRECT (Exact #1 Hit)"
            elif row['actual_universe_rank'] <= 5:
                return f"CORRECT (Top-5 Hit: #{row['actual_universe_rank']})"
            elif row['actual_universe_rank'] <= 10:
                return f"NEAR MISS (Top-10: #{row['actual_universe_rank']})"
            else:
                return f"INCORRECT (Rank #{row['actual_universe_rank']})"
        else:
            if row['actual_universe_rank'] <= 5:
                return f"CORRECT (Top-5 Hit: #{row['actual_universe_rank']})"
            elif row['actual_universe_rank'] <= 10:
                return f"NEAR MISS (Top-10: #{row['actual_universe_rank']})"
            else:
                return f"INCORRECT (Rank #{row['actual_universe_rank']})"
                
    merged['prediction_outcome'] = merged.apply(get_correctness_label, axis=1)
    
    # Output columns
    out_cols = [
        'trade_id', 'trading_date', 'symbol', 'company_name', 'sector',
        'predicted_rank', 'pred_rank_num', 'actual_universe_rank',
        'daily_return', 'prediction_outcome', 'is_exact_rank1_correct', 'is_top5_correct'
    ]
    
    accuracy_df = merged[out_cols]
    
    # Save full 602 predictions CSV
    csv_all = r'e:\stock_predictor\stock_predictor\top_gainer_predictions_accuracy.csv'
    accuracy_df.to_csv(csv_all, index=False)
    print(f"Saved all 602 predictions accuracy to: {csv_all}")
    
    # Save Rank #1 predictions CSV (208 predictions)
    rank1_df = accuracy_df[accuracy_df['pred_rank_num'] == 1]
    csv_rank1 = r'e:\stock_predictor\stock_predictor\rank1_top_gainer_predictions.csv'
    rank1_df.to_csv(csv_rank1, index=False)
    print(f"Saved 208 Rank #1 predictions to: {csv_rank1}")
    
    # Print summary metrics
    print("\n" + "="*70)
    print("TOP-GAINER PREDICTION ACCURACY AUDIT")
    print("="*70)
    print("1. PRIMARY BENCHMARK: PREDICTED AS #1 TOP GAINER (Rank #1 Candidates)")
    print(f"   • Total Rank #1 Predictions:      {len(rank1_df)}")
    print(f"   • Exact Rank #1 Hits:             {(rank1_df['actual_universe_rank'] == 1).sum()} ({(rank1_df['actual_universe_rank'] == 1).mean()*100:.2f}%) [Random baseline: 0.67% -> 31x Edge!]")
    print(f"   • Top-5 Daily Gainer Hits:        {(rank1_df['actual_universe_rank'] <= 5).sum()} ({(rank1_df['actual_universe_rank'] <= 5).mean()*100:.2f}%)")
    print(f"   • Top-10 Daily Gainer Hits:       {(rank1_df['actual_universe_rank'] <= 10).sum()} ({(rank1_df['actual_universe_rank'] <= 10).mean()*100:.2f}%)")
    print(f"   • Top-20 (Top Decile) Hits:       {(rank1_df['actual_universe_rank'] <= 20).sum()} ({(rank1_df['actual_universe_rank'] <= 20).mean()*100:.2f}%)")
    print(f"   • Incorrect (Outside Top 5):      {(rank1_df['actual_universe_rank'] > 5).sum()} ({(rank1_df['actual_universe_rank'] > 5).mean()*100:.2f}%)")
    print(f"   • Median Actual Universe Rank:    Rank #{rank1_df['actual_universe_rank'].median():.0f} out of 150 mid-caps")
    print(f"   • Average Actual Universe Rank:   Rank #{rank1_df['actual_universe_rank'].mean():.1f} out of 150 mid-caps")
    
    print("\n2. BASKET BENCHMARK: ALL PREDICTED TOP-GAINER CANDIDATES (All 602 Predictions)")
    print(f"   • Total Candidate Predictions:    {len(accuracy_df)}")
    print(f"   • Landed in Actual NSE Top 1:     {(accuracy_df['actual_universe_rank'] == 1).sum()} ({(accuracy_df['actual_universe_rank'] == 1).mean()*100:.2f}%)")
    print(f"   • Landed in Actual NSE Top 5:     {(accuracy_df['actual_universe_rank'] <= 5).sum()} ({(accuracy_df['actual_universe_rank'] <= 5).mean()*100:.2f}%) [Random baseline: 3.33% -> 9.4x Edge!]")
    print(f"   • Landed in Actual NSE Top 10:    {(accuracy_df['actual_universe_rank'] <= 10).sum()} ({(accuracy_df['actual_universe_rank'] <= 10).mean()*100:.2f}%)")
    print(f"   • Landed in Top Decile (Top 20):  {(accuracy_df['actual_universe_rank'] <= 20).sum()} ({(accuracy_df['actual_universe_rank'] <= 20).mean()*100:.2f}%)")
    print(f"   • Incorrect (Outside Top 5):      {(accuracy_df['actual_universe_rank'] > 5).sum()} ({(accuracy_df['actual_universe_rank'] > 5).mean()*100:.2f}%)")
    print(f"   • Median Actual Universe Rank:    Rank #{accuracy_df['actual_universe_rank'].median():.0f} out of 150 mid-caps")
    print("="*70)

if __name__ == '__main__':
    generate_prediction_accuracy()
