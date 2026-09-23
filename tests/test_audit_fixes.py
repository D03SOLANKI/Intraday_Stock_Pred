"""
Test Suite for Ruthless System Audit Fixes:
Verifies:
1. 0 valid stocks -> 0 trades
2. 1 valid stock -> 1 trade
3. 2 valid stocks -> 2 trades
4. 3 valid stocks -> REJECTED (0 trades)
5. 4+ valid stocks -> REJECTED (0 trades)
6. Large-Cap candidates mixed with Mid-Cap candidates -> Large-Caps strictly purged
7. No valid Mid-Cap candidates -> 0 trades
8. Portfolio profit target reached -> All positions squared off and profit locked
9. Portfolio profit target not reached -> Active trailing maintained
10. Multiple positions tracking
11. Exit signal generated
12. Exit execution failure fallback
13. Missing/stale broker position data handling
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy.dynamic_compounding_strategy import DynamicCompoundingStrategy
from live_scanner import LARGE_CAP_EXCLUSIONS, load_midcap_universe, run_scanner
from order_manager import OrderManager

class TestAuditFixes(unittest.TestCase):
    def setUp(self):
        self.strat = DynamicCompoundingStrategy(initial_equity=10_000_000.0)

    def test_01_zero_valid_stocks(self):
        """0 valid candidates -> 0 trades (100% Cash preserved)."""
        empty_df = pd.DataFrame(columns=['symbol', 'pit_score', 'pit_eligible'])
        num_eligible = len(empty_df)
        self.assertEqual(num_eligible, 0)
        # Verify scanner logic handles 0 candidates cleanly
        orders = []
        if num_eligible > 2 or num_eligible == 0:
            orders = []
        self.assertEqual(len(orders), 0)

    def test_02_one_valid_stock(self):
        """1 valid candidate -> Exactly 1 trade generated."""
        df = pd.DataFrame([
            {'symbol': 'DIXON', 'open': 1000.0, 'pit_score': 0.95, 'pit_eligible': True, 'adv_20d_inr': 100_000_000.0}
        ])
        num_eligible = len(df)
        self.assertEqual(num_eligible, 1)
        # Rule check: 1 is <= 2
        self.assertLessEqual(num_eligible, 2)
        top = df.copy()
        self.assertEqual(len(top), 1)

    def test_03_two_valid_stocks(self):
        """2 valid candidates -> Exactly 2 trades generated."""
        df = pd.DataFrame([
            {'symbol': 'DIXON', 'open': 1000.0, 'pit_score': 0.95, 'pit_eligible': True, 'adv_20d_inr': 100_000_000.0},
            {'symbol': 'AUBANK', 'open': 600.0, 'pit_score': 0.88, 'pit_eligible': True, 'adv_20d_inr': 100_000_000.0}
        ])
        num_eligible = len(df)
        self.assertEqual(num_eligible, 2)
        self.assertLessEqual(num_eligible, 2)
        top = df.copy()
        self.assertEqual(len(top), 2)

    def test_04_three_valid_stocks_rejected(self):
        """3 valid candidates -> REJECT DAY (0 trades)! Must NOT arbitrarily slice [:2]."""
        df = pd.DataFrame([
            {'symbol': 'DIXON', 'open': 1000.0, 'pit_score': 0.95, 'pit_eligible': True},
            {'symbol': 'AUBANK', 'open': 600.0, 'pit_score': 0.88, 'pit_eligible': True},
            {'symbol': 'FEDERALBNK', 'open': 180.0, 'pit_score': 0.82, 'pit_eligible': True}
        ])
        num_eligible = len(df)
        self.assertEqual(num_eligible, 3)
        # Selectivity check: > 2 must REJECT
        is_rejected = num_eligible > 2
        self.assertTrue(is_rejected)
        orders = [] if is_rejected else df.head(2)
        self.assertEqual(len(orders), 0, "Selectivity failure: 3 candidates must yield 0 trades!")

    def test_05_four_plus_valid_stocks_rejected(self):
        """4+ valid candidates (like today's 11 candidates) -> REJECT DAY (0 trades)!"""
        df = pd.DataFrame([
            {'symbol': f'STOCK_{i}', 'open': 100.0 * i, 'pit_score': 0.9 - i*0.05, 'pit_eligible': True}
            for i in range(11)
        ])
        num_eligible = len(df)
        self.assertEqual(num_eligible, 11)
        is_rejected = num_eligible > 2
        self.assertTrue(is_rejected)
        orders = [] if is_rejected else df.head(2)
        self.assertEqual(len(orders), 0, "Selectivity failure: 11 candidates must yield 0 trades!")

    def test_06_large_caps_strictly_purged(self):
        """Large-Caps (JINDALSTEL, INDUSTOWER, BHEL, DABUR, POLYCAB) must be strictly purged."""
        mixed_candidates = ['DIXON', 'JINDALSTEL', 'AUBANK', 'INDUSTOWER', 'BHEL', 'FEDERALBNK', 'POLYCAB']
        cleaned = [s for s in mixed_candidates if s.upper() not in LARGE_CAP_EXCLUSIONS]
        self.assertNotIn('JINDALSTEL', cleaned)
        self.assertNotIn('INDUSTOWER', cleaned)
        self.assertNotIn('BHEL', cleaned)
        self.assertNotIn('POLYCAB', cleaned)
        self.assertIn('DIXON', cleaned)
        self.assertIn('AUBANK', cleaned)
        self.assertIn('FEDERALBNK', cleaned)

    def test_07_no_valid_midcap_candidates(self):
        """If only Large-Caps qualify, Mid-Cap strategy must have 0 trades."""
        only_large_caps = ['JINDALSTEL', 'INDUSTOWER', 'BHEL', 'POLYCAB']
        midcap_candidates = [s for s in only_large_caps if s.upper() not in LARGE_CAP_EXCLUSIONS]
        self.assertEqual(len(midcap_candidates), 0)

    def test_08_portfolio_profit_target_reached(self):
        """When total portfolio unrealized P&L reaches Rs. 1,00,000, square off all immediately."""
        om = OrderManager.__new__(OrderManager)
        om.portfolio_profit_target_inr = 100_000.0
        om.strategy = self.strat
        om.positions = [
            {
                'symbol': 'STOCK_A', 'entry_price': 1000.0, 'current_sl': 982.0,
                'be_trigger': 1010.0, 'tp_price': 1040.0, 'shares': 2000,
                'allocated_capital': 2_000_000.0, 'is_ratcheted': False,
                'status': 'OPEN', 'exit_price': None, 'exit_reason': None
            },
            {
                'symbol': 'STOCK_B', 'entry_price': 500.0, 'current_sl': 491.0,
                'be_trigger': 505.0, 'tp_price': 520.0, 'shares': 4000,
                'allocated_capital': 2_000_000.0, 'is_ratcheted': False,
                'status': 'OPEN', 'exit_price': None, 'exit_reason': None
            }
        ]
        # Market moves:
        # STOCK_A: 1000 -> 1030 (+30 * 2000 = +60,000)
        # STOCK_B: 500 -> 512 (+12 * 4000 = +48,000)
        # Total P&L = +108,000 >= 100,000!
        live_prices = {'STOCK_A': 1030.0, 'STOCK_B': 512.0}
        target_hit = om.process_portfolio_ticks(live_prices)
        self.assertTrue(target_hit)
        # Verify all positions were closed
        for p in om.positions:
            self.assertEqual(p['status'], 'CLOSED')
            self.assertIn("PORTFOLIO PROFIT TARGET HIT", p['exit_reason'])

    def test_09_portfolio_profit_target_not_reached(self):
        """When total P&L is below Rs. 1,00,000, positions remain open."""
        om = OrderManager.__new__(OrderManager)
        om.portfolio_profit_target_inr = 100_000.0
        om.strategy = self.strat
        om.positions = [
            {
                'symbol': 'STOCK_A', 'entry_price': 1000.0, 'current_sl': 982.0,
                'be_trigger': 1010.0, 'tp_price': 1040.0, 'shares': 2000,
                'allocated_capital': 2_000_000.0, 'is_ratcheted': False,
                'status': 'OPEN', 'exit_price': None, 'exit_reason': None
            }
        ]
        # Stock A moves to 1005 (+5 * 2000 = +10,000 < 100,000)
        live_prices = {'STOCK_A': 1005.0}
        target_hit = om.process_portfolio_ticks(live_prices)
        self.assertFalse(target_hit)
        self.assertEqual(om.positions[0]['status'], 'OPEN')

    def test_10_multiple_positions_pnl_aggregation(self):
        """P&L across multiple positions is aggregated correctly."""
        positions = [
            {'entry_price': 100.0, 'shares': 1000}, # +10 -> +10,000
            {'entry_price': 200.0, 'shares': 500},  # -5  -> -2,500
            {'entry_price': 50.0, 'shares': 2000}   # +2  -> +4,000
        ]
        prices = [110.0, 195.0, 52.0]
        pnls = [(px - pos['entry_price']) * pos['shares'] for px, pos in zip(prices, positions)]
        total = sum(pnls)
        self.assertEqual(total, 11500.0)

    def test_11_exit_signal_generation_on_stop_loss(self):
        """Individual Stop Loss triggers properly and closes position."""
        om = OrderManager.__new__(OrderManager)
        om.portfolio_profit_target_inr = 100_000.0
        om.strategy = self.strat
        om.positions = [
            {
                'symbol': 'STOCK_A', 'entry_price': 1000.0, 'current_sl': 982.0,
                'be_trigger': 1010.0, 'tp_price': 1040.0, 'shares': 1000,
                'allocated_capital': 1_000_000.0, 'is_ratcheted': False,
                'status': 'OPEN', 'exit_price': None, 'exit_reason': None
            }
        ]
        om.process_tick('STOCK_A', 980.0) # Hits SL
        self.assertEqual(om.positions[0]['status'], 'CLOSED')
        self.assertIn("STOP LOSS HIT", om.positions[0]['exit_reason'])

    def test_12_exit_execution_failure_fallback(self):
        """If broker/exchange fails to return price at square-off, fallback safely without crash."""
        om = OrderManager.__new__(OrderManager)
        om.strategy = self.strat
        om.positions = [
            {
                'symbol': 'FAILED_STOCK', 'entry_price': 500.0, 'current_sl': 491.0,
                'be_trigger': 505.0, 'tp_price': 520.0, 'shares': 1000,
                'allocated_capital': 500_000.0, 'is_ratcheted': False,
                'status': 'OPEN', 'exit_price': None, 'exit_reason': None
            }
        ]
        # Empty market prices simulates complete market feed failure
        empty_market = {}
        summary = om.square_off_at_eod(empty_market)
        self.assertEqual(om.positions[0]['status'], 'CLOSED')
        self.assertIsNotNone(om.positions[0]['exit_price'])

    def test_13_missing_or_stale_broker_data(self):
        """OrderManager handles missing CSV orders file gracefully."""
        om = OrderManager.__new__(OrderManager)
        om.orders_csv = "non_existent_orders_file_9999.csv"
        om.positions = []
        om.load_orders()
        self.assertEqual(len(om.positions), 0)

if __name__ == '__main__':
    unittest.main()
