import math
from typing import Dict, Any, Optional
from config import strategy_config as cfg

def calculate_initial_stop_loss(
    entry_price: float,
    session_low: float,
    atr_14: float
) -> float:
    atr_stop = entry_price - (cfg.ATR_STOP_MULTIPLIER * atr_14)
    chosen_stop = max(session_low, atr_stop)
    
    max_allowed_risk_price = entry_price * (1.0 - cfg.MAX_INITIAL_STOP_LOSS_PCT)
    if chosen_stop < max_allowed_risk_price:
        chosen_stop = max_allowed_risk_price
        
    return chosen_stop

def calculate_position_size(
    portfolio_equity: float,
    entry_price: float,
    stop_loss_price: float,
    vol_20d_avg: float
) -> Dict[str, Any]:
    risk_per_share = max(entry_price - stop_loss_price, entry_price * 0.005)
    
    risk_capital = portfolio_equity * cfg.RISK_PER_TRADE_PCT
    shares_risk = risk_capital / risk_per_share
    
    max_position_capital = portfolio_equity * cfg.MAX_POSITION_WEIGHT_PCT
    shares_capital = max_position_capital / entry_price
    
    shares_volume = vol_20d_avg * cfg.MAX_ADV_PARTICIPATION_PCT
    
    final_shares = int(math.floor(min(shares_risk, shares_capital, shares_volume)))
    allocated_capital = final_shares * entry_price
    actual_risk_amount = final_shares * risk_per_share
    
    return {
        'shares': final_shares,
        'entry_price': entry_price,
        'stop_loss_price': stop_loss_price,
        'risk_per_share': risk_per_share,
        'allocated_capital': allocated_capital,
        'capital_weight_pct': (allocated_capital / portfolio_equity) * 100.0,
        'actual_risk_amount': actual_risk_amount,
        'risk_pct_of_equity': (actual_risk_amount / portfolio_equity) * 100.0
    }
