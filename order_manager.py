"""
Automated Intraday Order & Trailing Ratchet Manager
Tracks active positions during market hours (09:30 - 15:15 IST):
- Activates Dynamic +1.0% Breakeven Ratchet (moving stop to entry * 1.002)
- Enforces -1.8% Initial Stop Loss
- Executes +4.0% Primary Take Profit
- Automates 15:15 IST End-of-Day Square-Off
"""

import sys
import os
import time
import pandas as pd
import numpy as np
from strategy.dynamic_compounding_strategy import DynamicCompoundingStrategy

class OrderManager:
    def __init__(self, orders_csv: str = "daily_live_scan_orders.csv"):
        self.orders_csv = orders_csv
        self.strategy = DynamicCompoundingStrategy()
        self.positions = []
        self.load_orders()

    def load_orders(self):
        if not os.path.exists(self.orders_csv):
            print(f"No orders file found at {self.orders_csv}")
            return
        df = pd.read_csv(self.orders_csv)
        for _, row in df.iterrows():
            pos = {
                'symbol': row['Symbol'],
                'entry_price': float(row['Entry (Limit)']),
                'current_sl': float(row['Initial SL (-1.8%)']),
                'be_trigger': float(row['BE Trigger (+1.0%)']),
                'tp_price': float(row['Target (+4.0%)']),
                'shares': int(row['Shares']),
                'allocated_capital': float(row['Capital (Rs.)']),
                'is_ratcheted': False,
                'status': 'OPEN',
                'exit_price': None,
                'exit_reason': None
            }
            self.positions.append(pos)
        print(f"Loaded {len(self.positions)} active positions into Order Manager.")

    def process_tick(self, symbol: str, current_price: float):
        for pos in self.positions:
            if pos['symbol'] == symbol and pos['status'] == 'OPEN':
                entry = pos['entry_price']
                
                # Check Breakeven Ratchet (+1.0% MFE)
                if not pos['is_ratcheted'] and current_price >= pos['be_trigger']:
                    pos['current_sl'] = round(entry * (1.0 + self.strategy.breakeven_lock_pct), 2)
                    pos['is_ratcheted'] = True
                    print(f"[{symbol}] RATCHET ACTIVATED! Stop Loss raised to Breakeven (+0.20%): Rs. {pos['current_sl']:,.2f}")
                    
                # Check Stop Loss Trigger
                if current_price <= pos['current_sl']:
                    pos['status'] = 'CLOSED'
                    pos['exit_price'] = current_price * (1.0 - self.strategy.exit_slippage_pct)
                    pos['exit_reason'] = 'BREAKEVEN RATCHET HIT' if pos['is_ratcheted'] else 'STOP LOSS HIT'
                    print(f"[{symbol}] EXIT: {pos['exit_reason']} at Rs. {pos['exit_price']:,.2f}")
                    
                # Check Take Profit Trigger
                elif current_price >= pos['tp_price']:
                    pos['status'] = 'CLOSED'
                    pos['exit_price'] = pos['tp_price'] * (1.0 - self.strategy.exit_slippage_pct)
                    pos['exit_reason'] = 'TAKE PROFIT HIT'
                    print(f"[{symbol}] EXIT: TAKE PROFIT at Rs. {pos['exit_price']:,.2f}")

    def square_off_at_eod(self, market_prices: dict):
        print("\n" + "=" * 80)
        print("15:15 IST MANDATORY INTRADAY SQUARE-OFF EXECUTION")
        print("=" * 80)
        closed_trades = []
        
        for pos in self.positions:
            sym = pos['symbol']
            if pos['status'] == 'OPEN':
                mkt_px = market_prices.get(sym, pos['entry_price'])
                pos['status'] = 'CLOSED'
                pos['exit_price'] = mkt_px * (1.0 - self.strategy.exit_slippage_pct)
                pos['exit_reason'] = 'INTRADAY SQUARE OFF (15:15 IST)'
                print(f"[{sym}] Intraday Auto-Square-Off at Rs. {pos['exit_price']:,.2f}")
                
            # Reconcile PnL
            buy_val = pos['shares'] * pos['entry_price']
            sell_val = pos['shares'] * pos['exit_price']
            gross_pnl = sell_val - buy_val
            charges = self.strategy.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
            net_pnl = gross_pnl - charges['total_charges']
            ret_pct = (net_pnl / buy_val) * 100.0
            
            closed_trades.append({
                'Symbol': sym,
                'Shares': pos['shares'],
                'Entry (Rs.)': pos['entry_price'],
                'Exit (Rs.)': round(pos['exit_price'], 2),
                'Exit Reason': pos['exit_reason'],
                'Ratcheted': pos['is_ratcheted'],
                'Gross PnL (Rs.)': round(gross_pnl, 2),
                'Statutory Charges (Rs.)': round(charges['total_charges'], 2),
                'Net PnL (Rs.)': round(net_pnl, 2),
                'Return %': round(ret_pct, 2)
            })
            
        summary_df = pd.DataFrame(closed_trades)
        summary_df.to_csv("daily_trade_execution_summary.csv", index=False)
        print("\nDaily Execution Summary:")
        print(summary_df[['Symbol', 'Exit Reason', 'Net PnL (Rs.)', 'Return %']].to_string())
        print(f"\nTotal Net PnL Today: Rs. {summary_df['Net PnL (Rs.)'].sum():,.2f}")
        return summary_df

if __name__ == "__main__":
    om = OrderManager()
    # Test simulation of price progression
    test_market = {
        'ICICIPRULI': 505.0,  # +2.0% (Triggers BE Ratchet and closes in profit)
        'INDUSTOWER': 378.0,  # -0.9% (In trade, closes at square off)
        'GVT&D': 4490.0,      # +2.1% (Triggers BE Ratchet and closes in profit)
        'JUBLFOOD': 475.0     # -2.0% (Hits initial Stop Loss)
    }
    for s, px in test_market.items():
        om.process_tick(s, px)
    om.square_off_at_eod(test_market)
