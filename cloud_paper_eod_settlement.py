"""
Cloud Paper Trading 15:15 IST EOD Settlement Script
Executes automated square-off and trailing stop resolution in GitHub Actions
Runs when the user's laptop is powered off.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from order_manager import OrderManager
import yfinance as yf

def run_eod_settlement():
    print("=" * 80)
    print("CLOUD PAPER TRADING: 15:15 IST EOD SETTLEMENT & RECONCILIATION")
    print(f"Timestamp: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST")
    print("=" * 80)

    om = OrderManager()
    open_positions = [p for p in om.positions if p['status'] == 'OPEN']

    if not open_positions:
        print("[INFO] No open paper positions to square off today. Portfolio is 100% Cash.")
        return

    print(f"[INFO] Found {len(open_positions)} active open paper positions:")
    for p in open_positions:
        print(f"  - {p['symbol']} | Entry: Rs. {p['entry_price']:,.2f} | Shares: {p['shares']:,}")

    tickers = [f"{p['symbol']}.NS" for p in open_positions]
    mkt_prices = {}

    try:
        data = yf.download(tickers, period="1d", interval="5m", progress=False)
        if not data.empty and 'Close' in data:
            if isinstance(data['Close'], pd.DataFrame):
                last_row = data['Close'].iloc[-1]
                for p in open_positions:
                    t = f"{p['symbol']}.NS"
                    if t in last_row and not pd.isna(last_row[t]):
                        mkt_prices[p['symbol']] = float(last_row[t])
            elif isinstance(data['Close'], pd.Series):
                sym = open_positions[0]['symbol']
                mkt_prices[sym] = float(data['Close'].iloc[-1])
    except Exception as e:
        print(f"[WARNING] Could not fetch real-time close ticks: {e}")

    # Fallback to entry price if market tick unavailable
    for p in open_positions:
        if p['symbol'] not in mkt_prices:
            mkt_prices[p['symbol']] = p['entry_price']

    # Execute square-off
    summary_df = om.square_off_at_eod(mkt_prices, reason="CLOUD INTRADAY SQUARE OFF (15:15 IST)")
    print(f"\nSettlement complete. Summary recorded to daily_trade_execution_summary.csv")
    print(f"New Paper Portfolio Cash Balance: Rs. {om.state['cash_balance']:,.2f}")
    print(f"New Paper Realized P&L: Rs. {om.state['total_realized_pnl']:+,.2f}")

if __name__ == "__main__":
    run_eod_settlement()
