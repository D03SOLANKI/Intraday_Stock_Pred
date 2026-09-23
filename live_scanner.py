"""
Production 09:30 AM Point-in-Time Live Scanner
Fetches live market data from NSE via yfinance or evaluates historical panels,
applying Tier 4 Dynamic Compounding sizing with the 5% ADV liquidity guardrail.
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

IST = timezone(timedelta(hours=5, minutes=30))

from strategy.dynamic_compounding_strategy import DynamicCompoundingStrategy

CATALYST_SYMBOLS = [
    'NIACL', 'GICRE', 'TATAINVEST', 'GVT&D', 'JSL', 'JINDALSTEL', 'BSE', 'IDEA', 'INDUSTOWER', 
    'APARINDS', 'RVNL', 'BHEL', 'WAAREEENER', 'PATANJALI', 'AWL', 'DABUR', 'POLYCAB', 'THERMAX', 
    'SUZLON', 'TATACOMM', 'VOLTAS', 'KPRMILL', 'POLICYBZR', 'SJVN', 'JUBLFOOD', 'HONAUT', 'GODREJIND'
]

def fetch_live_market_candidates(symbols: list = None) -> pd.DataFrame:
    """
    Downloads live intraday 15m and daily historical bars for midcap universe.
    """
    import yfinance as yf
    
    if symbols is None:
        symbols = CATALYST_SYMBOLS
        
    tickers = [f"{s}.NS" for s in symbols]
    print(f"Downloading live daily & 15m data for {len(tickers)} mid-cap tickers from NSE...")
    
    try:
        daily_data = yf.download(tickers, period="2mo", interval="1d", progress=False)
        intraday_data = yf.download(tickers, period="1d", interval="15m", progress=False)
    except Exception as e:
        print(f"Error downloading live market data: {e}")
        return pd.DataFrame()
        
    rows = []
    for sym in symbols:
        t = f"{sym}.NS"
        try:
            if t not in daily_data['Close'].columns or t not in intraday_data['Open'].columns:
                continue
                
            c_series = daily_data['Close'][t].dropna()
            v_series = daily_data['Volume'][t].dropna()
            if len(c_series) < 15:
                continue
                
            prev_close = float(c_series.iloc[-2]) if len(c_series) > 1 else float(c_series.iloc[-1])
            sma20 = float(c_series.iloc[-20:].mean())
            dist_sma20 = ((prev_close - sma20) / sma20) * 100.0
            adv_20d = float((c_series.iloc[-20:] * v_series.iloc[-20:]).median())
            
            intra_open = intraday_data['Open'][t].dropna()
            intra_high = intraday_data['High'][t].dropna()
            intra_low = intraday_data['Low'][t].dropna()
            intra_close = intraday_data['Close'][t].dropna()
            intra_vol = intraday_data['Volume'][t].dropna()
            
            if intra_open.empty:
                continue
                
            o_15m = float(intra_open.iloc[0])
            h_15m = float(intra_high.iloc[0])
            l_15m = float(intra_low.iloc[0])
            c_15m = float(intra_close.iloc[-1])
            v_15m = float(intra_vol.sum())
            
            if pd.isna(o_15m) or o_15m == 0:
                continue
                
            gap_pct = (o_15m - prev_close) / prev_close
            gap_rejected = l_15m >= (prev_close * 0.998)
            expected_15m_vol = (adv_20d / prev_close) / 25.0
            vol_thrust = (v_15m / (expected_15m_vol + 1e-6))
            
            pit_score = (
                0.40 * (gap_pct / 0.01) +
                0.30 * (1.0 / (abs(dist_sma20) + 0.01)) +
                0.20 * 1.0 +
                0.10 * min(3.0, vol_thrust)
            )
            
            rows.append({
                'symbol': sym,
                'prev_close': prev_close,
                'open': o_15m,
                'high': h_15m,
                'low': l_15m,
                'close': c_15m,
                'volume': v_15m,
                'gap_pct': gap_pct,
                'gap_rejected': gap_rejected,
                'dist_sma20': dist_sma20,
                'vol_thrust': vol_thrust,
                'adv_20d_inr': adv_20d,
                'pit_score': pit_score,
                'pit_eligible': gap_rejected and (gap_pct >= 0.003)
            })
        except Exception:
            continue
            
    df_live = pd.DataFrame(rows)
    return df_live

def run_scanner(trading_date: str = None, active_equity: float = 10_000_000.0, data_path: str = "all_midcap_stock_days_5year.pkl", force_live: bool = False):
    print("=" * 80)
    print("POINT-IN-TIME 09:30 AM MID-CAP SCANNER (TIER 4 DYNAMIC COMPOUNDING)")
    print(f"Active Portfolio Equity: Rs. {active_equity:,.2f}")
    now_ist = datetime.now(IST)
    print(f"Execution Timestamp: {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
    print("=" * 80)
    
    strat = DynamicCompoundingStrategy(initial_equity=active_equity)
    
    # Check if live market data should be fetched
    is_live_hours = (now_ist.weekday() < 5) and (now_ist.hour >= 9)
    eligible = None
    
    if force_live or (trading_date is None and is_live_hours):
        print("Attempting LIVE market scan via NSE real-time feed...")
        live_df = fetch_live_market_candidates()
        if not live_df.empty:
            eligible = live_df[live_df['pit_eligible']].sort_values(by='pit_score', ascending=False)
            print(f"Live market candidates qualifying: {len(eligible)}")
            
    # Fallback to historical file if live data returned empty
    if eligible is None or len(eligible) == 0:
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Data file {data_path} not found.")
        print(f"Loading historical market panel from {data_path}...")
        df = pd.read_pickle(data_path)
        df_feat = strat.compute_pit_features(df)
        all_dates = sorted(df_feat['date'].unique())
        target_date = trading_date if trading_date in all_dates else all_dates[-1]
        print(f"Scanning session: {target_date}")
        day_df = df_feat[df_feat['date'] == target_date].copy()
        eligible = day_df[day_df['pit_eligible']].sort_values(by='pit_score', ascending=False)
        
    if len(eligible) == 0:
        print("\n[INFO] Zero candidates met entry criteria. 100% Cash preserved.")
        pd.DataFrame().to_csv("daily_live_scan_orders.csv", index=False)
        return pd.DataFrame()
        
    top_candidates = eligible.head(strat.max_concurrent_positions).copy()
    
    orders = []
    print("\n" + "-" * 80)
    print("ACTIONABLE 09:30 AM BUY ORDERS GENERATED (TIER 4 CONVICTION SIZING)")
    print("-" * 80)
    
    for rank_idx, (_, row) in enumerate(top_candidates.iterrows(), 1):
        sym = row['symbol']
        open_px = row['open']
        entry_price = open_px * (1.0 + strat.entry_slippage_pct)
        initial_sl = entry_price * (1.0 - strat.initial_stop_loss_pct)
        be_trigger = entry_price * (1.0 + strat.breakeven_trigger_pct)
        tp_price = entry_price * (1.0 + strat.take_profit_pct)
        
        adv_20d = row.get('adv_20d_inr', 50_000_000.0)
        allocated_cap, shares = strat.calculate_position_size(active_equity, adv_20d, open_px)
        adv_cap_pct = (allocated_cap / adv_20d) * 100 if adv_20d > 0 else 0.0
        
        orders.append({
            'Rank': f"#{rank_idx}",
            'Symbol': sym,
            'Scan Date': now_ist.strftime('%Y-%m-%d'),
            'Scan Time': now_ist.strftime('%H:%M:%S IST'),
            'Entry (Limit)': round(entry_price, 2),
            'Initial SL (-1.8%)': round(initial_sl, 2),
            'BE Trigger (+1.0%)': round(be_trigger, 2),
            'Target (+4.0%)': round(tp_price, 2),
            'Shares': shares,
            'Capital (Rs.)': round(allocated_cap, 2),
            'Equity %': round((allocated_cap / active_equity) * 100, 1),
            'ADV %': round(adv_cap_pct, 2)
        })
        
        print(f"Rank #{rank_idx}: [{sym}] | Limit Price: Rs. {entry_price:,.2f} | Shares: {shares:,}")
        print(f"   Allocated: Rs. {allocated_cap:,.2f} ({(allocated_cap/active_equity)*100:.1f}% Equity, {adv_cap_pct:.1f}% ADV)")
        print(f"   Hard SL: Rs. {initial_sl:,.2f} | Ratchet Trigger: Rs. {be_trigger:,.2f} | Target: Rs. {tp_price:,.2f}")
        
    orders_df = pd.DataFrame(orders)
    orders_df.to_csv("daily_live_scan_orders.csv", index=False)
    print("\nOrders saved to daily_live_scan_orders.csv")
    return orders_df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live 09:30 AM Midcap Strategy Scanner")
    parser.add_argument("--date", type=str, default=None, help="Trading date (YYYY-MM-DD)")
    parser.add_argument("--equity", type=float, default=10_000_000.0, help="Active portfolio equity (INR)")
    parser.add_argument("--live", action="store_true", help="Force live market download")
    args = parser.parse_args()
    
    run_scanner(trading_date=args.date, active_equity=args.equity, force_live=args.live)
