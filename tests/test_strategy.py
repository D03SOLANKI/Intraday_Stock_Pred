import unittest
import pandas as pd
import numpy as np
from strategy.rules import (
    check_layer1_premarket,
    check_layer2_intraday,
    check_volume_trap_exclusion,
    check_layer3_persistence
)
from strategy.position_sizer import calculate_initial_stop_loss, calculate_position_size

class TestMidCapStrategy(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range('2026-01-01', periods=30)
        prices = [100.0 + (np.sin(i) * 0.5) for i in range(30)]
        # 100 * 1,500,000 = 150,000,000 INR (>= 10 Cr floor)
        volumes = [1500000 for _ in range(30)]
        self.df_hist = pd.DataFrame({
            'close': prices,
            'high': [p + 1.0 for p in prices],
            'low': [p - 1.0 for p in prices],
            'volume': volumes
        }, index=dates)

    def test_layer1_coiling_pass(self):
        res = check_layer1_premarket(self.df_hist, headlines=['Company emerges as L1 Bidder for mega project'])
        self.assertTrue(res['passed']) 
        self.assertEqual(res['matched_keyword'], 'L1 BIDDER')

    def test_layer1_no_catalyst_fail(self):
        res = check_layer1_premarket(self.df_hist, headlines=['Ordinary retail meeting concluded'])
        self.assertFalse(res['passed'])
        self.assertEqual(res['reason'], 'no_verified_catalyst')

    def test_layer2_gap_and_volume_pass(self):
        res = check_layer2_intraday(
            open_price=101.0,
            prev_close=100.0,
            current_price=102.5,
            orb_high=101.5,
            current_vwap=101.8,
            cum_vol_30m=150000,
            vol_20d_avg=500000
        )
        self.assertTrue(res['passed'])

    def test_layer2_gap_too_large_fail(self):
        res = check_layer2_intraday(
            open_price=104.0,
            prev_close=100.0,
            current_price=104.5,
            orb_high=104.2,
            current_vwap=104.0,
            cum_vol_30m=150000,
            vol_20d_avg=500000
        )
        self.assertFalse(res['passed'])
        self.assertEqual(res['reason'], 'failed_gap_screen')


    def test_volume_trap_exclusion(self):
        is_trap = check_volume_trap_exclusion(vol_ratio=2.5, range_pos=0.20)
        self.assertTrue(is_trap)
        
        is_accum = check_volume_trap_exclusion(vol_ratio=2.5, range_pos=0.85)
        self.assertFalse(is_accum)


    def test_layer3_persistence_qualification(self):
        res = check_layer3_persistence(range_pos=0.82, vol_ratio=2.4, alpha_spread=4.2)
        self.assertTrue(res['qualifies_swing'])
        self.assertEqual(res['action'], 'CONVERT_TO_SWING')

    def test_position_sizing_caps(self):
        sizing = calculate_position_size(
            portfolio_equity=10000000,
            entry_price=100.0,
            stop_loss_price=98.0,
            vol_20d_avg=500000
        )
        self.assertEqual(sizing['shares'], 10000)

if __name__ == '__main__':
    unittest.main()
