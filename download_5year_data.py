import os
import sys
import time
import pandas as pd
import yfinance as yf

def download_5year_historical_data():
    print("Reading NIFTY Midcap 150 constituents...")
    n150 = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    symbols = n150['Symbol'].dropna().unique().tolist()
    
    # Format Yahoo ticker symbols (.NS suffix)
    yahoo_tickers = [f"{s}.NS" for s in symbols]
    # Also add benchmarks: NIFTY 50 (^NSEI) and NIFTY MIDCAP 150 / 50 benchmark
    benchmark_tickers = ['^NSEI', 'NIFTY_MIDCAP_100.NS']
    all_tickers = yahoo_tickers + benchmark_tickers
    
    print(f"Total tickers to download: {len(all_tickers)} (150 Midcap stocks + benchmarks)...")
    
    start_date = '2021-08-01' # 2-month warmup for rolling 50-DMA
    end_date = '2026-09-20'
    
    # Download in batches of 25
    batch_size = 25
    dfs = []
    
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
        print(f"Downloading batch {i//batch_size + 1}/{(len(all_tickers) + batch_size - 1)//batch_size}: {len(batch)} tickers...")
        try:
            raw = yf.download(
                batch,
                start=start_date,
                end=end_date,
                group_by='ticker',
                progress=False,
                auto_adjust=False
            )
            if not raw.empty:
                dfs.append(raw)
        except Exception as e:
            print(f"Error downloading batch {i}: {e}")
        time.sleep(0.5)
        
    print("Combining downloaded batches...")
    full_df = pd.concat(dfs, axis=1)
    
    out_path = r'e:\stock_predictor\stock_predictor\midcap_150_raw_prices_5year.pkl'
    full_df.to_pickle(out_path)
    print(f"Successfully saved 5-year raw price matrix to: {out_path}")
    print(f"Shape: {full_df.shape}, Index range: {full_df.index.min()} to {full_df.index.max()}")
    
    return full_df

if __name__ == '__main__':
    download_5year_historical_data()
