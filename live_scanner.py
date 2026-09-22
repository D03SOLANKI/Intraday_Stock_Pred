"""
Production 09:30 AM Point-in-Time Scanner
Executes daily at 09:30:05 IST to scan the NIFTY Midcap 150 universe,
applying Tier 4 Dynamic Compounding sizing with the 5% ADV liquidity guardrail.
"""

import sys
import os
import argparse
import pandas as pd
import numpy as np
from strategy.dynamic_compounding_strategy import DynamicCompoundingStrategy

def run_scanner(trading_date: str = None, active_equity: float = 10_000_000.0, data_path: str = "all_midcap_stock_days_5year.pkl"):
    print("=" * 80)
    print(f"POINT-IN-TIME 09:30 AM MID-CAP SCANNER (TIER 4 DYNAMIC COMPOUNDING)")
    print(f"Active Portfolio Equity: Rs. {active_equity:,.2f}")
    print("=" * 80)
    
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Data file {data_path} not found.")
        
    print(f"Loading market panel from {data_path}...")
    df = pd.read_pickle(data_path)
    
    strat = DynamicCompoundingStrategy(initial_equity=active_equity)
    df_feat = strat.compute_pit_features(df)
    
    all_dates = sorted(df_feat['date'].unique())
    if trading_date is None:
        trading_date = all_dates[-1]
        print(f"No date specified; scanning most recent trading session: {trading_date}")
    else:
        if trading_date not in all_dates:
            print(f"Warning: {trading_date} not found. Using closest available session.")
            trading_date = min(all_dates, key=lambda d: abs(pd.to_datetime(d) - pd.to_datetime(trading_date)))
            print(f"Selected session: {trading_date}")
            
    day_df = df_feat[df_feat['date'] == trading_date].copy()
    print(f"Evaluated {len(day_df)} mid-cap stocks for session {trading_date}.")
    
    # Filter eligible stocks
    eligible = day_df[day_df['pit_eligible']].sort_values(by='pit_score', ascending=False)
    print(f"Candidates meeting all 09:30 AM Point-in-Time Filters: {len(eligible)}")
    
    if len(eligible) == 0:
        print("\n[INFO] Zero candidates met entry criteria today. Preservation of capital active (100% Cash).")
        return eligible
        
    # Top 4 slots for Tier 4
    top_candidates = eligible.head(strat.max_concurrent_positions).copy()
    
    orders = []
    print("\n" + "-" * 80)
    print("ACTIONABLE 09:30 AM BUY ORDERS GENERATED (TIER 4 CONVICTION SIZING)")
    print("-" * 80)
    
    for rank_idx, (_, row) in enumerate(top_candidates.iterrows(), 1):
        sym = row['symbol']
        open_15m = row['open']
        entry_price = open_15m * (1.0 + strat.entry_slippage_pct)
        initial_sl = entry_price * (1.0 - strat.initial_stop_loss_pct)
        be_trigger = entry_price * (1.0 + strat.breakeven_trigger_pct)
        tp_price = entry_price * (1.0 + strat.take_profit_pct)
        
        # Liquidity ADV Cap Check
        adv_20d = row.get('adv_20d_inr', 50_000_000.0)
        allocated_cap, shares = strat.calculate_position_size(active_equity, adv_20d, open_15m)
        adv_cap_pct = (allocated_cap / adv_20d) * 100 if adv_20d > 0 else 0.0
        
        orders.append({
            'Rank': f"#{rank_idx}",
            'Symbol': sym,
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
    args = parser.parse_args()
    
    run_scanner(trading_date=args.date, active_equity=args.equity)
