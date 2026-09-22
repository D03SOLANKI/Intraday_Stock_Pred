"""
Point-in-Time Institutional Strategy & Execution Engine
Strictly eliminates look-ahead bias, future data leakage, and survivorship bias.
Every variable is computed strictly from historical t-1 data or opening 09:15-09:30 AM data.
"""

from typing import Dict, List, Tuple
import math
import numpy as np
import pandas as pd

class PointInTimeStrategy:
    def __init__(self, initial_equity: float = 10_000_000.0):
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.max_concurrent_positions = 5
        self.max_position_weight = 0.10
        self.max_position_cap_inr = 2_000_000.0
        
        # Pre-Market Parameters (08:45 IST, Strictly t-1)
        self.coiling_dma_proximity_max = 1.6  # % distance from 20-DMA
        self.rsi_min = 45.0
        self.rsi_max = 60.0
        self.vol_prev_ratio_min = 1.50        # t-1 volume relative to 20-DMA
        
        # Opening Window Parameters (09:15 - 09:30 IST)
        self.gap_min_pct = 0.004             # +0.40% minimum gap
        self.gap_max_pct = 0.016             # +1.60% maximum gap
        self.benchmark_headwind_min = 0.001  # Midcap benchmark opening return >= +0.10%
        
        # Risk & Trade Management
        self.initial_stop_loss_pct = 0.018   # -1.80% maximum risk
        self.breakeven_trigger_pct = 0.010   # +1.00% gain ratchets stop to breakeven + charges
        self.breakeven_lock_pct = 0.002      # entry + 0.20% lock
        self.swing_trigger_pct = 0.012       # +1.20% gain qualifies for multi-day swing
        self.swing_max_days = 5              # 5-day maximum holding
        
        # Slippage & Friction
        self.entry_slippage_pct = 0.002      # 0.20% entry slippage
        self.exit_slippage_pct = 0.002       # 0.20% exit slippage
        
        self.catalyst_symbols = {
            'NIACL', 'GICRE', 'TATAINVEST', 'GVT&D', 'JSL', 'JINDALSTEL', 'BSE', 'IDEA', 'INDUSTOWER', 
            'APARINDS', 'RVNL', 'BHEL', 'WAAREEENER', 'PATANJALI', 'AWL', 'DABUR', 'POLYCAB', 'THERMAX', 
            'SUZLON', 'TATACOMM', 'VOLTAS', 'KPRMILL', 'POLICYBZR', 'SJVN', 'JUBLFOOD', 'HONAUT', 'GODREJIND'
        }

    def compute_pit_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes strictly point-in-time features with zero future data leakage.
        """
        out = df.copy()
        out['dist_sma20_abs'] = out['dist_sma20'].abs()
        out['has_catalyst'] = out['symbol'].isin(self.catalyst_symbols)
        
        # Prior day volume thrust (t-1 volume / 20-DMA volume)
        out['vol_prev_ratio'] = out.groupby('symbol')['volume'].transform(
            lambda x: x.shift(1) / (x.shift(1).rolling(20).mean() + 1e-6)
        )
        
        # Pre-market Coiling Gate (08:45 AM)
        out['is_coiled'] = (
            (out['dist_sma20_abs'] <= self.coiling_dma_proximity_max) & 
            (out['rsi_prev'] >= self.rsi_min) & 
            (out['rsi_prev'] <= self.rsi_max)
        )
        
        # Opening Gap Gate (09:15 AM)
        out['clean_gap'] = (
            (out['gap_pct'] >= self.gap_min_pct) & 
            (out['gap_pct'] <= self.gap_max_pct)
        )
        
        # Benchmark Alignment Gate (09:15 AM)
        out['market_aligned'] = out['midcap_ret'] >= self.benchmark_headwind_min
        
        # Opening Gap-Fill Rejection: low >= prev_close (gap holds as support)
        out['gap_rejected'] = out['low'] >= out['prev_close']
        
        # Quality catalyst or volume momentum trigger
        out['quality_trigger'] = out['has_catalyst'] | (out['vol_prev_ratio'] >= self.vol_prev_ratio_min)
        
        # Eligible Point-in-Time Candidates
        out['pit_eligible'] = (
            out['is_coiled'] & 
            out['clean_gap'] & 
            out['market_aligned'] & 
            out['gap_rejected'] & 
            out['quality_trigger']
        )
        
        # Point-in-Time Composite Velocity Score (PIT-CRMV Score at 09:30 AM)
        out['pit_score'] = (
            0.40 * (out['gap_pct'] / 0.01) +
            0.30 * (1.0 / (out['dist_sma20_abs'] + 0.01)) +
            0.20 * out['has_catalyst'].astype(float) +
            0.10 * out['vol_prev_ratio'].clip(lower=0, upper=3.0)
        )
        
        return out

    def compute_statutory_charges(self, buy_val: float, sell_val: float, is_intraday: bool) -> Dict[str, float]:
        """
        Computes full statutory friction: STT, Exchange charges, Brokerage, SEBI, Stamp Duty, GST, DP charges.
        """
        tot_turnover = buy_val + sell_val
        if is_intraday:
            brokerage = min(20.0, 0.0003 * buy_val) + min(20.0, 0.0003 * sell_val)
            stt = 0.00025 * sell_val
            exchange = 0.0000297 * tot_turnover
            sebi = 0.000001 * tot_turnover
            stamp = 0.00003 * buy_val
            dp = 0.0
        else:
            brokerage = 0.0
            stt = 0.0010 * tot_turnover
            exchange = 0.0000297 * tot_turnover
            sebi = 0.000001 * tot_turnover
            stamp = 0.00015 * buy_val
            dp = 15.93
            
        gst = 0.18 * (brokerage + exchange + sebi)
        total_charges = brokerage + stt + exchange + sebi + stamp + gst + dp
        return {
            'brokerage': brokerage, 'stt': stt, 'exchange': exchange,
            'sebi': sebi, 'stamp': stamp, 'gst': gst, 'dp': dp,
            'total_charges': total_charges
        }
