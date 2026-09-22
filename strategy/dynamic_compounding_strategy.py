"""
Tier 4 Dynamic Compounding Institutional Strategy Engine
Capital Allocation:
- 28% Equity Sizing per Position
- Maximum 4 Concurrent Positions
- 5% 20-day Average Daily Volume (ADV) Liquidity Ceiling
- Dynamic +1.0% Breakeven Ratchet (+0.20% locked in)
- Point-in-Time 09:30 AM Entry (Zero Look-Ahead Bias)
"""

from typing import Dict, List, Tuple
import math
import numpy as np
import pandas as pd

class DynamicCompoundingStrategy:
    def __init__(self, initial_equity: float = 10_000_000.0):
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.position_equity_weight = 0.28    # Tier 4: 28% of active equity per position
        self.max_concurrent_positions = 4     # Max 4 concurrent slots
        self.max_adv_participation = 0.05     # Strict 5% 20-day ADV liquidity limit
        
        # Pre-Market Parameters (08:45 IST, Strictly t-1)
        self.coiling_dma_proximity_max = 2.5  # 20-DMA proximity threshold
        self.rsi_min = 45.0
        self.rsi_max = 60.0
        self.vol_prev_ratio_min = 1.50        # t-1 volume relative to 20-DMA
        
        # Opening Window Parameters (09:15 - 09:30 IST)
        self.gap_min_pct = 0.004              # +0.40% minimum opening gap
        self.gap_max_pct = 0.016              # +1.60% maximum opening gap
        
        # Risk & Trade Management
        self.initial_stop_loss_pct = 0.018    # -1.80% maximum risk
        self.breakeven_trigger_pct = 0.010    # +1.00% gain ratchets stop to breakeven + charges
        self.breakeven_lock_pct = 0.002       # entry + 0.20% lock
        self.take_profit_pct = 0.040          # +4.00% primary intraday profit target
        
        # Execution & Slippage
        self.entry_slippage_pct = 0.002       # 0.20% adverse entry slippage
        self.exit_slippage_pct = 0.002        # 0.20% adverse exit slippage
        
        self.catalyst_symbols = {
            'NIACL', 'GICRE', 'TATAINVEST', 'GVT&D', 'JSL', 'JINDALSTEL', 'BSE', 'IDEA', 'INDUSTOWER', 
            'APARINDS', 'RVNL', 'BHEL', 'WAAREEENER', 'PATANJALI', 'AWL', 'DABUR', 'POLYCAB', 'THERMAX', 
            'SUZLON', 'TATACOMM', 'VOLTAS', 'KPRMILL', 'POLICYBZR', 'SJVN', 'JUBLFOOD', 'HONAUT', 'GODREJIND'
        }

    def compute_pit_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes point-in-time signals and ADV caps with zero future data leakage.
        """
        out = df.copy()
        out['dist_sma20_abs'] = out['dist_sma20'].abs()
        out['has_catalyst'] = out['symbol'].isin(self.catalyst_symbols)
        
        # Prior day volume thrust (t-1 volume / 20-DMA volume)
        out['vol_prev_ratio'] = out.groupby('symbol')['volume'].transform(
            lambda x: x.shift(1) / (x.shift(1).rolling(20).mean() + 1e-6)
        )
        
        # 20-day Average Daily Turnover (Volume * Close) strictly known before market open
        if 'vol_20d' in out.columns:
            out['adv_20d_inr'] = out['vol_20d'] * out['prev_close']
        else:
            out['adv_20d_inr'] = out.groupby('symbol')['volume'].transform(
                lambda x: x.shift(1).rolling(20).median()
            ) * out['prev_close']
            
        out['adv_20d_inr'] = out['adv_20d_inr'].fillna(50_000_000.0)
        
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
        
        # Opening Gap-Fill Rejection: low >= prev_close (gap holds as support)
        out['gap_rejected'] = out['low'] >= (out['prev_close'] * 0.998)
        
        # Quality catalyst or volume momentum trigger
        out['quality_trigger'] = out['has_catalyst'] | (out['vol_prev_ratio'] >= self.vol_prev_ratio_min)
        
        # Eligible Point-in-Time Candidates
        out['pit_eligible'] = (
            out['is_coiled'] & 
            out['clean_gap'] & 
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

    def calculate_position_size(self, current_equity: float, adv_20d: float, share_price: float) -> Tuple[float, int]:
        """
        Calculates position capital and share quantity using 28% equity sizing
        bounded by the strict 5% ADV liquidity ceiling.
        """
        target_capital = current_equity * self.position_equity_weight
        max_liquidity_capital = adv_20d * self.max_adv_participation if adv_20d > 0 else target_capital
        
        allocated_capital = min(target_capital, max_liquidity_capital)
        shares = int(allocated_capital / (share_price * (1.0 + self.entry_slippage_pct)))
        actual_capital = shares * share_price * (1.0 + self.entry_slippage_pct)
        
        return actual_capital, shares

    def compute_statutory_charges(self, buy_val: float, sell_val: float, is_intraday: bool = True) -> Dict[str, float]:
        """
        Computes statutory Indian market charges: STT, Exchange charges, Brokerage, SEBI, Stamp Duty, GST, DP charges.
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
