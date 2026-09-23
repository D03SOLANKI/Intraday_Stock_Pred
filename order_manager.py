"""
Option 3: Production Machine Learning Top-3 Gainer Paper Trading Order Manager
Manages paper orders and active positions during and after market hours:
- Tracks Option 3 predictions (TGPI Score, Top-3 Probability)
- Enforces -2.5% Initial Stop Loss
- Activates Dynamic Trailing Stop once gain reaches +4.0% (trailing 3.5% from peak)
- Computes complete statutory charges (STT, GST, SEBI fee, exchange charges, stamp duty, slippage)
- Maintains persistent paper portfolio state in paper_trading_state.json and paper_trades_history.csv
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

IST = timezone(timedelta(hours=5, minutes=30))

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy.ml_top3_gainer_strategy import MLTop3GainerStrategy

STATE_FILE = os.path.join(PROJECT_ROOT, "paper_trading_state.json")
ORDERS_FILE = os.path.join(PROJECT_ROOT, "daily_live_scan_orders.csv")
SUMMARY_FILE = os.path.join(PROJECT_ROOT, "daily_trade_execution_summary.csv")
HISTORY_FILE = os.path.join(PROJECT_ROOT, "paper_trades_history.csv")


class OrderManager:
    def __init__(self, orders_csv: str = ORDERS_FILE, initial_capital: float = 10_000_000.0):
        self.orders_csv = orders_csv
        self.strategy = MLTop3GainerStrategy(initial_equity=initial_capital)
        self.initial_capital = initial_capital
        self.state = self.load_portfolio_state()
        self.positions = self.state.get("open_positions", [])
        self.load_orders()

    def load_portfolio_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "initial_capital": self.initial_capital,
            "cash_balance": self.initial_capital,
            "total_equity": self.initial_capital,
            "total_realized_pnl": 0.0,
            "total_trades_completed": 0,
            "open_positions": [],
            "last_updated": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        }

    def save_portfolio_state(self):
        self.state["open_positions"] = [p for p in self.positions if p.get("status") == "OPEN"]
        self.state["last_updated"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"Error saving portfolio state: {e}")

    def load_orders(self):
        if not os.path.exists(self.orders_csv):
            print(f"[OrderManager] No orders file found at {self.orders_csv}")
            return

        try:
            df = pd.read_csv(self.orders_csv)
            if df.empty:
                return

            existing_symbols = {p['symbol'] for p in self.positions if p['status'] == 'OPEN'}

            for _, row in df.iterrows():
                sym = str(row['Symbol']).strip().upper()
                if sym in existing_symbols:
                    continue

                # Support both ML Top-3 and legacy columns gracefully
                entry_px = float(row.get('Entry Limit (₹)', row.get('Entry (Limit)', row.get('Entry', 0.0))))
                if entry_px <= 0:
                    continue

                shares = int(row.get('Shares', 0))
                capital = float(row.get('Capital (₹)', row.get('Capital (Rs.)', row.get('Capital', shares * entry_px))))
                initial_sl = float(row.get('Stop Loss (₹)', row.get('Initial SL (-2.5%)', row.get('Initial SL (-1.8%)', entry_px * 0.975))))
                tgpi = float(row.get('TGPI Score', 0.0))
                top3_prob = float(row.get('Top-3 Prob %', 0.0))

                pos = {
                    'rank': str(row.get('Rank', f"#{len(self.positions)+1}")),
                    'symbol': sym,
                    'entry_date': datetime.now(IST).strftime("%Y-%m-%d"),
                    'entry_time': datetime.now(IST).strftime("%H:%M:%S"),
                    'entry_price': entry_px,
                    'shares': shares,
                    'allocated_capital': capital,
                    'initial_sl': round(initial_sl, 2),
                    'current_sl': round(initial_sl, 2),
                    'trailing_trigger': round(entry_px * (1.0 + self.strategy.trailing_activation_pct), 2), # +4.0%
                    'highest_price_seen': entry_px,
                    'is_trailing_active': False,
                    'tgpi_score': tgpi,
                    'top3_prob': top3_prob,
                    'status': 'OPEN',
                    'exit_price': None,
                    'exit_time': None,
                    'exit_reason': None,
                    'trade_logic': str(row.get('Trade Logic', '')),
                    'key_drivers': str(row.get('Key Drivers', '')),
                    'volume_surge': str(row.get('Volume Surge', '')),
                    'range_position': str(row.get('Range Position', '')),
                    'sector_alpha': str(row.get('Sector Alpha', '')),
                    'dist_20dma': str(row.get('Dist 20-DMA', '')),
                    'rsi': str(row.get('RSI', ''))
                }

                # Deduct cash for paper purchase
                if self.state["cash_balance"] >= capital:
                    self.state["cash_balance"] -= capital
                self.positions.append(pos)
                existing_symbols.add(sym)
                print(f"[PAPER TRADE ENTRY] {sym} | Shares: {shares:,} @ Rs. {entry_px:,.2f} | Capital: Rs. {capital:,.2f}")

            self.save_portfolio_state()
            print(f"[OrderManager] Active open positions: {len([p for p in self.positions if p['status'] == 'OPEN'])}")

        except Exception as e:
            print(f"[OrderManager] Error loading orders: {e}")

    def process_tick(self, symbol: str, current_price: float, current_time_str: str = None) -> dict:
        """
        Processes a real-time price tick for a symbol.
        Enforces Option 3 runner dynamics:
        1. Tracks peak price (highest_price_seen).
        2. Activates Trailing Stop when price >= entry * 1.04 (+4.0%).
        3. Trails stop at highest_price_seen * 0.965 (peak - 3.5%).
        4. Exits if price <= current_sl.
        """
        if current_time_str is None:
            current_time_str = datetime.now(IST).strftime("%H:%M:%S")

        for pos in self.positions:
            if pos['symbol'] == symbol and pos['status'] == 'OPEN':
                entry = pos['entry_price']

                # Update highest price seen
                if current_price > pos['highest_price_seen']:
                    pos['highest_price_seen'] = current_price

                # Check if Trailing Stop Trigger is reached (+4.0% gain)
                if not pos['is_trailing_active'] and pos['highest_price_seen'] >= pos['trailing_trigger']:
                    pos['is_trailing_active'] = True
                    new_sl = round(pos['highest_price_seen'] * (1.0 - self.strategy.trailing_step_pct), 2)
                    pos['current_sl'] = max(pos['current_sl'], new_sl)
                    print(f"[{symbol}] RUNNER ACTIVE! Trailing stop initiated at Rs. {pos['current_sl']:,.2f} (Peak: Rs. {pos['highest_price_seen']:,.2f})")

                # If trailing is active, ratchet the stop higher as price moves up
                if pos['is_trailing_active']:
                    dynamic_sl = round(pos['highest_price_seen'] * (1.0 - self.strategy.trailing_step_pct), 2)
                    if dynamic_sl > pos['current_sl']:
                        pos['current_sl'] = dynamic_sl
                        print(f"[{symbol}] TRAILING SL RATCHETED UP -> Rs. {pos['current_sl']:,.2f} (Peak: Rs. {pos['highest_price_seen']:,.2f})")

                # Check Stop Loss / Trailing Stop breach
                if current_price <= pos['current_sl']:
                    exit_px = current_price * (1.0 - self.strategy.exit_slippage_pct)
                    exit_reason = "TRAILING STOP HIT" if pos['is_trailing_active'] else "INITIAL SL HIT (-2.5%)"
                    self._close_position(pos, exit_px, exit_reason, current_time_str)
                    return pos

        return None

    def process_portfolio_ticks(self, live_prices: dict) -> list:
        closed_this_tick = []
        open_positions = [p for p in self.positions if p['status'] == 'OPEN']
        now_str = datetime.now(IST).strftime("%H:%M:%S")

        for pos in open_positions:
            sym = pos['symbol']
            if sym in live_prices:
                closed = self.process_tick(sym, live_prices[sym], now_str)
                if closed:
                    closed_this_tick.append(closed)

        self.save_portfolio_state()
        return closed_this_tick

    def _close_position(self, pos: dict, exit_price: float, exit_reason: str, exit_time_str: str):
        pos['status'] = 'CLOSED'
        pos['exit_price'] = round(exit_price, 2)
        pos['exit_time'] = exit_time_str
        pos['exit_reason'] = exit_reason

        buy_val = pos['shares'] * pos['entry_price']
        sell_val = pos['shares'] * pos['exit_price']
        gross_pnl = sell_val - buy_val

        # Deduct statutory charges
        charges = self.strategy.compute_statutory_charges(buy_val, sell_val, is_intraday=True)
        total_charges = charges['total_charges']
        net_pnl = gross_pnl - total_charges
        ret_pct = (net_pnl / buy_val) * 100.0 if buy_val > 0 else 0.0

        pos['gross_pnl'] = round(gross_pnl, 2)
        pos['statutory_charges'] = round(total_charges, 2)
        pos['net_pnl'] = round(net_pnl, 2)
        pos['return_pct'] = round(ret_pct, 2)

        # Update paper balance
        proceeds = sell_val - total_charges
        self.state["cash_balance"] += proceeds
        self.state["total_realized_pnl"] += net_pnl
        self.state["total_trades_completed"] += 1

        print(f"\n[PAPER TRADE CLOSED] {pos['symbol']} | Exit: Rs. {exit_price:,.2f} | Reason: {exit_reason}")
        print(f"                     Net P&L: Rs. {net_pnl:+,.2f} ({ret_pct:+.2f}%) | Charges: Rs. {total_charges:,.2f}")

        self._record_closed_trade(pos)
        self.save_portfolio_state()

    def _record_closed_trade(self, pos: dict):
        record = {
            'Symbol': pos['symbol'],
            'Shares': pos['shares'],
            'Entry (Rs.)': pos['entry_price'],
            'Exit (Rs.)': pos['exit_price'],
            'Exit Reason': pos['exit_reason'],
            'Ratcheted': pos['is_trailing_active'],
            'Gross PnL (Rs.)': pos['gross_pnl'],
            'Statutory Charges (Rs.)': pos['statutory_charges'],
            'Net PnL (Rs.)': pos['net_pnl'],
            'Return %': pos['return_pct'],
            'Date': pos.get('entry_date', datetime.now(IST).strftime("%Y-%m-%d")),
            'Exit Time': pos.get('exit_time', datetime.now(IST).strftime("%H:%M:%S"))
        }

        # Append to master history
        if os.path.exists(HISTORY_FILE):
            hist_df = pd.read_csv(HISTORY_FILE)
            hist_df = pd.concat([hist_df, pd.DataFrame([record])], ignore_index=True)
        else:
            hist_df = pd.DataFrame([record])
        hist_df.to_csv(HISTORY_FILE, index=False)

        # Update daily summary
        closed_today = [p for p in self.positions if p['status'] == 'CLOSED']
        if closed_today:
            today_records = []
            for p in closed_today:
                today_records.append({
                    'Symbol': p['symbol'],
                    'Shares': p['shares'],
                    'Entry (Rs.)': p['entry_price'],
                    'Exit (Rs.)': p['exit_price'],
                    'Exit Reason': p['exit_reason'],
                    'Ratcheted': p['is_trailing_active'],
                    'Gross PnL (Rs.)': p.get('gross_pnl', 0.0),
                    'Statutory Charges (Rs.)': p.get('statutory_charges', 0.0),
                    'Net PnL (Rs.)': p.get('net_pnl', 0.0),
                    'Return %': p.get('return_pct', 0.0)
                })
            pd.DataFrame(today_records).to_csv(SUMMARY_FILE, index=False)

    def square_off_at_eod(self, market_prices: dict, reason: str = "INTRADAY SQUARE OFF (15:15 IST)"):
        print("\n" + "=" * 80)
        print(f"PAPER TRADING EXECUTION: {reason}")
        print("=" * 80)
        now_str = datetime.now(IST).strftime("%H:%M:%S")

        open_positions = [p for p in self.positions if p['status'] == 'OPEN']
        for pos in open_positions:
            sym = pos['symbol']
            mkt_px = market_prices.get(sym, pos['entry_price'])
            exit_px = mkt_px * (1.0 - self.strategy.exit_slippage_pct)
            self._close_position(pos, exit_px, reason, now_str)

        self.save_portfolio_state()
        if os.path.exists(SUMMARY_FILE):
            return pd.read_csv(SUMMARY_FILE)
        return pd.DataFrame()


if __name__ == "__main__":
    om = OrderManager()
    print("Order Manager initialized successfully.")
    print(f"Open positions: {len([p for p in om.positions if p['status'] == 'OPEN'])}")
    print(f"Cash balance: Rs. {om.state['cash_balance']:,.2f}")
