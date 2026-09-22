import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from config import strategy_config as cfg

def compute_rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df['high'] if 'high' in df.columns else df['High']
    low = df['low'] if 'low' in df.columns else df['Low']
    close = df['close'] if 'close' in df.columns else df['Close']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window).mean()

def check_layer1_premarket(df_hist: pd.DataFrame, headlines: Optional[List[str]] = None) -> Dict[str, Any]:
    close_col = 'close' if 'close' in df_hist.columns else 'Close'
    vol_col = 'volume' if 'volume' in df_hist.columns else 'Volume'
    
    if len(df_hist) < 20:
        return {'passed': False, 'reason': 'insufficient_history'}
        
    close_series = df_hist[close_col]
    vol_series = df_hist[vol_col]
    
    close_t1 = close_series.iloc[-1]
    sma20 = close_series.tail(20).mean()
    dist_sma20 = abs(close_t1 - sma20) / sma20
    
    if dist_sma20 > cfg.COILING_DMA_PROXIMITY_PCT:
        return {'passed': False, 'reason': 'failed_20dma_proximity', 'dist_sma20': dist_sma20}
        
    high_10d = close_series.tail(10).max()
    low_10d = close_series.tail(10).min()
    range_10d = (high_10d - low_10d) / (close_t1 + 1e-6)
    if range_10d > cfg.COILING_RANGE_10D_MAX:
        return {'passed': False, 'reason': 'failed_10d_range_coiling', 'range_10d': range_10d}
        
    rsi_series = compute_rsi(close_series, 14)
    rsi_t1 = rsi_series.iloc[-1]
    if pd.notnull(rsi_t1) and not (cfg.RSI_14_MIN <= rsi_t1 <= cfg.RSI_14_MAX):
        return {'passed': False, 'reason': 'failed_rsi_neutrality', 'rsi_t1': rsi_t1}
        
    turnover_20d = (close_series.tail(20) * vol_series.tail(20)).mean()
    if turnover_20d < cfg.TURNOVER_20D_MIN_INR:
        return {'passed': False, 'reason': 'failed_liquidity_floor', 'turnover_20d': turnover_20d}
        
    has_catalyst = True
    matched_keyword = None
    if headlines is not None:
        has_catalyst = False
        for h in headlines:
            h_upper = str(h).upper()
            for kw in cfg.CATALYST_KEYWORDS:
                if kw in h_upper:
                    has_catalyst = True
                    matched_keyword = kw
                    break
            if has_catalyst:
                break
        if not has_catalyst:
            return {'passed': False, 'reason': 'no_verified_catalyst'}
            
    atr_14 = compute_atr(df_hist, 14).iloc[-1] if len(df_hist) >= 15 else (close_t1 * 0.02)
    vol_20d_avg = vol_series.tail(20).mean()
    
    return {
        'passed': True,
        'close_t1': close_t1,
        'sma20': sma20,
        'dist_sma20': dist_sma20,
        'range_10d': range_10d,
        'rsi_t1': rsi_t1,
        'vol_20d_avg': vol_20d_avg,
        'atr_14': atr_14,
        'matched_keyword': matched_keyword
    }

def check_layer2_intraday(
    open_price: float,
    prev_close: float,
    current_price: float,
    orb_high: float,
    current_vwap: float,
    cum_vol_30m: float,
    vol_20d_avg: float,
    upper_circuit: Optional[float] = None
) -> Dict[str, Any]:
    gap_pct = (open_price - prev_close) / prev_close
    
    if not (cfg.GAP_MIN_PCT <= gap_pct <= cfg.GAP_MAX_PCT):
        return {'passed': False, 'reason': 'failed_gap_screen', 'gap_pct': gap_pct}
        
    if upper_circuit and current_price >= (upper_circuit * (1.0 - cfg.UPPER_CIRCUIT_BUFFER_PCT)):
        return {'passed': False, 'reason': 'circuit_limit_reached'}
        
    if cum_vol_30m < (cfg.VOL_VELOCITY_30M_PCT * vol_20d_avg):
        return {'passed': False, 'reason': 'failed_volume_velocity', 'cum_vol_30m': cum_vol_30m}
        
    if not (current_price > orb_high and current_price > current_vwap):
        return {'passed': False, 'reason': 'failed_orb_vwap_breakout'}
        
    return {
        'passed': True,
        'gap_pct': gap_pct,
        'current_price': current_price,
        'entry_price': current_price
    }

def check_volume_trap_exclusion(vol_ratio: float, range_pos: float) -> bool:
    if (vol_ratio >= cfg.VOLUME_TRAP_VOL_RATIO_MIN) and (range_pos < cfg.VOLUME_TRAP_RANGE_POS_MAX):
        return True
    return False

def check_layer3_persistence(range_pos: float, vol_ratio: float, alpha_spread: float) -> Dict[str, Any]:
    if check_volume_trap_exclusion(vol_ratio, range_pos):
        return {'qualifies_swing': False, 'action': 'EMERGENCY_ABORT_VOLUME_TRAP'}
        
    passes_range = range_pos >= cfg.RANGE_POS_MIN_L3
    passes_vol = vol_ratio >= cfg.VOL_RATIO_MIN_L3
    passes_alpha = alpha_spread >= cfg.ALPHA_SPREAD_MIN_L3
    
    qualifies = passes_range and passes_vol and passes_alpha
    return {
        'qualifies_swing': qualifies,
        'action': 'CONVERT_TO_SWING' if qualifies else 'SQUARE_OFF_INTRADAY',
        'passes_range': passes_range,
        'passes_vol': passes_vol,
        'passes_alpha': passes_alpha,
        'range_pos': range_pos,
        'vol_ratio': vol_ratio,
        'alpha_spread': alpha_spread
    }
