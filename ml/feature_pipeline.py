import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import pandas as pd
import numpy as np

def build_point_in_time_features(df_raw: pd.DataFrame, n150_csv: str = 'nifty_midcap_150.csv') -> pd.DataFrame:
    """
    Builds strictly point-in-time features for all mid-cap stocks across all dates.
    Zero future information is present in features.
    Target labels (next-day return & rank) are constructed strictly for evaluation & training.
    """
    print("Building Point-in-Time Feature Pipeline...")
    
    # Load official midcap universe
    n150 = pd.read_csv(n150_csv)
    from strategy.improved_point_in_time_strategy import NIFTY100_LARGE_CAP_EXCLUSIONS
    
    valid_symbols = set(n150['Symbol'].dropna().unique()) - NIFTY100_LARGE_CAP_EXCLUSIONS
    print(f"Purged Mid-Cap Universe: {len(valid_symbols)} stocks.")
    
    # Filter dataset for valid midcap symbols
    df = df_raw[df_raw['symbol'].isin(valid_symbols)].copy()
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)
    
    # Calculate group-wise technical features
    grouped = df.groupby('symbol', group_keys=False)
    
    # 1. Price Momentum & Returns (Day T and earlier)
    df['ret_1d'] = df['daily_return'] # (close - prev_close)/prev_close * 100
    df['ret_3d'] = grouped['close'].transform(lambda x: (x / x.shift(3) - 1.0) * 100.0)
    df['ret_5d'] = grouped['close'].transform(lambda x: (x / x.shift(5) - 1.0) * 100.0)
    df['ret_10d'] = grouped['close'].transform(lambda x: (x / x.shift(10) - 1.0) * 100.0)
    df['ret_20d'] = grouped['close'].transform(lambda x: (x / x.shift(20) - 1.0) * 100.0)
    
    # 2. Moving Average Proximity
    df['sma_20'] = grouped['close'].transform(lambda x: x.rolling(20).mean())
    df['sma_50'] = grouped['close'].transform(lambda x: x.rolling(50).mean())
    df['dist_sma20_feat'] = (df['close'] - df['sma_20']) / (df['sma_20'] + 1e-6) * 100.0
    df['dist_sma50_feat'] = (df['close'] - df['sma_50']) / (df['sma_50'] + 1e-6) * 100.0
    df['sma20_trend'] = grouped['sma_20'].transform(lambda x: (x / x.shift(5) - 1.0) * 100.0)
    
    # 3. Volatility & Price Compression
    df['true_range_pct'] = (df['high'] - df['low']) / (df['prev_close'] + 1e-6) * 100.0
    df['atr_5d'] = grouped['true_range_pct'].transform(lambda x: x.rolling(5).mean())
    df['atr_20d'] = grouped['true_range_pct'].transform(lambda x: x.rolling(20).mean())
    df['compression_ratio'] = df['atr_5d'] / (df['atr_20d'] + 1e-6) # Coiling indicator
    
    # 4. Volume Acceleration & Liquidity
    df['vol_sma20'] = grouped['volume'].transform(lambda x: x.rolling(20).mean())
    df['vol_sma5'] = grouped['volume'].transform(lambda x: x.rolling(5).mean())
    df['vol_surge_t'] = df['volume'] / (df['vol_sma20'] + 1e-6)
    df['vol_accel_feat'] = df['vol_sma5'] / (df['vol_sma20'] + 1e-6)
    df['adv_20d_cr'] = (df['close'] * df['vol_sma20']) / 10_000_000.0 # in Crores
    
    # 5. Range Placement on Day T
    range_span = df['high'] - df['low']
    df['range_position'] = np.where(range_span > 0, (df['close'] - df['low']) / range_span, 0.5)
    
    # 6. Sector & Benchmark Relative Strength
    sector_mean = df.groupby(['sector', 'date'])['daily_return'].transform('mean')
    df['stock_vs_sector'] = df['daily_return'] - sector_mean
    
    # 7. Next-Day Target Label Generation (Future T+1, strictly for training/eval)
    df['target_next_day_return'] = grouped['daily_return'].shift(-1)
    df['target_next_gap_pct'] = grouped['gap_pct'].shift(-1)
    
    # Drop rows without next-day return (the last available trading day)
    df = df.dropna(subset=['target_next_day_return', 'dist_sma50_feat']).copy()
    
    # Calculate Next-Day Rank on Date T+1 across the universe
    df['target_next_rank'] = df.groupby('date')['target_next_day_return'].rank(ascending=False, method='min')
    df['target_is_top1'] = (df['target_next_rank'] == 1).astype(int)
    df['target_is_top3'] = (df['target_next_rank'] <= 3).astype(int)
    df['target_is_top5'] = (df['target_next_rank'] <= 5).astype(int)
    df['target_is_top10'] = (df['target_next_rank'] <= 10).astype(int)
    
    # LambdaMART relevance label (0 to 4)
    df['target_relevance'] = np.select(
        [df['target_next_rank'] == 1, df['target_next_rank'] == 2, df['target_next_rank'] == 3, df['target_next_rank'] <= 5],
        [4, 3, 2, 1],
        default=0
    )
    
    print(f"Features successfully built: {len(df):,} valid stock-days across {df['date'].nunique()} trading sessions.")
    return df

if __name__ == '__main__':
    raw = pd.read_pickle('all_midcap_stock_days_5year.pkl')
    feat = build_point_in_time_features(raw)
    feat.to_pickle('ml/engineered_features_dataset.pkl')
    print("Saved to ml/engineered_features_dataset.pkl")
