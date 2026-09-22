import os
import sys
import pandas as pd
import numpy as np

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def build_5year_panel_dataset():
    raw_path = r'e:\stock_predictor\stock_predictor\midcap_150_raw_prices_5year.pkl'
    if not os.path.exists(raw_path):
        print(f"Error: {raw_path} not found!")
        return None
        
    print(f"Loading raw prices from {raw_path}...")
    raw_df = pd.read_pickle(raw_path)
    
    n150 = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    comp_map = dict(zip(n150['Symbol'], n150['Company Name']))
    sec_map = dict(zip(n150['Symbol'], n150['Industry']))
    
    # Extract benchmark series (^NSEI)
    nifty_close = None
    if '^NSEI' in raw_df.columns:
        nifty_close = raw_df['^NSEI']['Close'].copy()
    elif ('^NSEI', 'Close') in raw_df.columns:
        nifty_close = raw_df[('^NSEI', 'Close')].copy()
        
    if nifty_close is not None:
        nifty_ret = nifty_close.pct_change() * 100.0
    else:
        nifty_ret = pd.Series(0.0, index=raw_df.index)
        
    # Process each symbol
    tickers = [c for c in raw_df.columns.levels[0] if c not in ['^NSEI', 'NIFTY_MIDCAP_100.NS']]
    print(f"Processing panel data across {len(tickers)} midcap symbols...")
    
    stock_dfs = []
    
    for t in tickers:
        sym = t.replace('.NS', '')
        t_data = raw_df[t].copy().dropna(how='all')
        if t_data.empty or len(t_data) < 30:
            continue
            
        t_data = t_data.sort_index()
        t_data = t_data.loc[~t_data.index.duplicated(keep='last')]
        
        close = t_data['Close']
        open_p = t_data['Open']
        high = t_data['High']
        low = t_data['Low']
        volume = t_data['Volume'].fillna(0)
        
        prev_close = close.shift(1)
        daily_return = (close - prev_close) / prev_close * 100.0
        intraday_return = (close - open_p) / open_p * 100.0
        gap_pct = (open_p - prev_close) / prev_close
        
        # Volume moving averages (strictly historical shift 1)
        vol_5d = volume.shift(1).rolling(5, min_periods=3).mean()
        vol_20d = volume.shift(1).rolling(20, min_periods=5).mean().fillna(volume.expanding().mean())
        vol_50d = volume.shift(1).rolling(50, min_periods=10).mean()
        vol_ratio = volume / (vol_20d + 1e-6)
        
        # Range position: location of close within session high-low
        day_range = high - low
        rng_pos = np.where(day_range > 0, (close - low) / (day_range + 1e-6), 0.5)
        
        # Technical indicators (strictly historical shift 1)
        sma20 = close.rolling(20, min_periods=5).mean()
        dist_sma20 = (prev_close - sma20.shift(1)) / (sma20.shift(1) + 1e-6) * 100.0
        
        rsi_series = calculate_rsi(close, 14)
        rsi_prev = rsi_series.shift(1).fillna(50.0)
        
        roll_52w = high.rolling(252, min_periods=30).max()
        dist_52w = (prev_close - roll_52w.shift(1)) / (roll_52w.shift(1) + 1e-6) * 100.0
        
        # Combine
        stock_df = pd.DataFrame({
            'date': t_data.index.strftime('%Y-%m-%d'),
            'symbol': sym,
            'company': comp_map.get(sym, sym),
            'sector': sec_map.get(sym, 'Mid-Cap Equities'),
            'prev_close': prev_close,
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'daily_return': daily_return,
            'intraday_return': intraday_return,
            'gap_pct': gap_pct,
            'volume': volume,
            'vol_5d': vol_5d,
            'vol_20d': vol_20d,
            'vol_50d': vol_50d,
            'vol_ratio': vol_ratio,
            'rng_pos': rng_pos,
            'rsi_prev': rsi_prev,
            'dist_sma20': dist_sma20,
            'dist_52w_high': dist_52w
        })
        
        # Drop warm-up rows where prev_close or volume is missing
        stock_df = stock_df.dropna(subset=['prev_close', 'close', 'open', 'high', 'low'])
        stock_dfs.append(stock_df)
        
    print("Concatenating full 5-year panel dataset...")
    full_panel = pd.concat(stock_dfs, ignore_index=True)
    
    # Filter to exact 5-year target window: 2021-09-19 to 2026-09-19
    full_panel = full_panel[(full_panel['date'] >= '2021-09-19') & (full_panel['date'] <= '2026-09-19')]
    full_panel = full_panel.sort_values(['date', 'symbol']).reset_index(drop=True)
    
    # Compute benchmark midcap daily return per date
    midcap_avg_ret = full_panel.groupby('date')['daily_return'].transform('mean')
    full_panel['midcap_ret'] = midcap_avg_ret
    full_panel['alpha_vs_midcap'] = full_panel['daily_return'] - full_panel['midcap_ret']
    
    # Identify Daily Top 5 Gainers
    print("Identifying daily Top 5 midcap gainers for every session...")
    full_panel['rank'] = full_panel.groupby('date')['daily_return'].rank(ascending=False, method='min').astype(int)
    full_panel['is_top5'] = full_panel['rank'] <= 5
    
    # Save panel dataset
    panel_path = r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl'
    full_panel.to_pickle(panel_path)
    print(f"Saved 5-year panel dataset to: {panel_path}")
    print(f"Total stock-days: {len(full_panel):,} across {full_panel['date'].nunique()} trading sessions.")
    
    # Extract and save Top 5 daily enriched CSV
    top5_df = full_panel[full_panel['is_top5']].sort_values(['date', 'rank']).reset_index(drop=True)
    top5_path = r'e:\stock_predictor\stock_predictor\top5_daily_5year_enriched.csv'
    top5_df.to_csv(top5_path, index=False)
    print(f"Saved Top 5 daily dataset to: {top5_path} ({len(top5_df):,} records across {top5_df['date'].nunique()} sessions).")
    
    return full_panel, top5_df

if __name__ == '__main__':
    build_5year_panel_dataset()
