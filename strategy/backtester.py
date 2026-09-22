import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from config import strategy_config as cfg
from strategy.rules import (
    check_layer1_premarket,
    check_layer2_intraday,
    check_volume_trap_exclusion,
    check_layer3_persistence
)
from strategy.position_sizer import calculate_initial_stop_loss, calculate_position_size

class BacktestEngine:
    def __init__(
        self,
        all_stock_days_df: pd.DataFrame,
        top5_enriched_df: pd.DataFrame,
        initial_equity: float = cfg.PORTFOLIO_INITIAL_EQUITY
    ):
        self.all_data = all_stock_days_df.copy()
        self.top5_data = top5_enriched_df.copy()
        self.equity = initial_equity
        self.initial_equity = initial_equity
        self.active_positions = []
        self.completed_trades = []
        self.daily_equity_curve = []
        
    def run(self) -> Dict[str, Any]:
        unique_dates = sorted(self.all_data['date'].unique())
        print(f'Starting backtest across {len(unique_dates)} sessions...')
        
        for d in unique_dates:
            day_df = self.all_data[self.all_data['date'] == d]
            if day_df.empty:
                continue
                
            midcap_ret = day_df['midcap_ret'].iloc[0] if 'midcap_ret' in day_df.columns else 0.0
            
            # --- 1. Manage existing multi-day swing positions ---
            self._manage_swings(d, day_df)
            
            # --- Benchmark Headwind Protection (Skip new entries if midcap benchmark <= -0.50%) ---
            headwind_limit = getattr(cfg, 'MIDCAP_HEADWIND_MIN_PCT', -0.005)
            if midcap_ret < headwind_limit:
                self.daily_equity_curve.append({'date': d, 'equity': self.equity})
                continue
            
            # --- 2. Layer 1: Pre-market scanning ---
            l1_candidates = []
            for _, row in day_df.iterrows():
                # Check pre-move coiling
                dist_sma = abs(row['dist_sma20']) / 100.0 if pd.notnull(row['dist_sma20']) else 0.5
                range_coiling = 0.03 # baseline coiling
                rsi_prev = row['rsi_prev'] if pd.notnull(row['rsi_prev']) else 50.0
                
                if dist_sma <= cfg.COILING_DMA_PROXIMITY_PCT and (cfg.RSI_14_MIN <= rsi_prev <= cfg.RSI_14_MAX):
                    l1_candidates.append(row)
                    
            # --- 3. Layer 2: Intraday candidate evaluation & CRMV Ranking ---
            l2_passing = []
            for cand in l1_candidates:
                sym = cand['symbol']
                if any(p['symbol'] == sym for p in self.active_positions):
                    continue # already open
                    
                prev_close = cand['prev_close']
                open_price = cand['open']
                gap_pct = (open_price - prev_close) / prev_close
                
                # Check gap bounds
                if not (cfg.GAP_MIN_PCT <= gap_pct <= cfg.GAP_MAX_PCT):
                    continue
                    
                # Volume expansion check (Calibrated to 1.60x)
                vol_ratio = cand['vol_ratio'] if pd.notnull(cand['vol_ratio']) else 1.0
                vol_threshold = getattr(cfg, 'VOL_RATIO_MIN_L2', 1.60)
                if vol_ratio < vol_threshold:
                    continue
                    
                # Negative control volume trap check
                range_pos = cand['rng_pos'] if pd.notnull(cand['rng_pos']) else 0.5
                if check_volume_trap_exclusion(vol_ratio, range_pos):
                    continue # rejected by Volume Trap!
                
                l2_passing.append(cand)
                
            # Apply CRMV Cross-Sectional Ranking Engine
            if getattr(cfg, 'USE_CRMV_RANKING', True) and len(l2_passing) > 1:
                l2_df = pd.DataFrame(l2_passing)
                v_norm = (l2_df['vol_ratio'] - l2_df['vol_ratio'].mean()) / (l2_df['vol_ratio'].std() + 1e-6)
                r_norm = (l2_df['rng_pos'] - l2_df['rng_pos'].mean()) / (l2_df['rng_pos'].std() + 1e-6)
                g_gap = ((l2_df['open'] - l2_df['prev_close']) / l2_df['prev_close'])
                g_norm = (g_gap - g_gap.mean()) / (g_gap.std() + 1e-6)
                c_dist = l2_df['dist_sma20'].abs() / 100.0 if 'dist_sma20' in l2_df.columns else pd.Series(0.01, index=l2_df.index)
                inv_c = 1.0 / (c_dist + 0.005)
                c_norm = (inv_c - inv_c.mean()) / (inv_c.std() + 1e-6)
                
                w_v = getattr(cfg, 'CRMV_WEIGHT_VOLUME', 0.45)
                w_r = getattr(cfg, 'CRMV_WEIGHT_RANGE_POS', 0.35)
                w_g = getattr(cfg, 'CRMV_WEIGHT_GAP', 0.10)
                w_c = getattr(cfg, 'CRMV_WEIGHT_COILING', 0.10)
                
                l2_df['crmv_score'] = w_v * v_norm + w_r * r_norm + w_g * g_norm + w_c * c_norm
                ordered_candidates = [row for _, row in l2_df.sort_values('crmv_score', ascending=False).iterrows()]
            else:
                ordered_candidates = l2_passing

            for cand in ordered_candidates:
                if len(self.active_positions) >= cfg.MAX_CONCURRENT_POSITIONS:
                    break
                    
                sym = cand['symbol']
                if any(p['symbol'] == sym for p in self.active_positions):
                    continue
                    
                prev_close = cand['prev_close']
                open_price = cand['open']
                vol_ratio = cand['vol_ratio'] if pd.notnull(cand['vol_ratio']) else 1.0
                range_pos = cand['rng_pos'] if pd.notnull(cand['rng_pos']) else 0.5
                    
                entry_price = open_price * 1.003 # include 0.3% entry slippage
                session_low = cand['low']
                atr = prev_close * 0.02
                stop_loss = calculate_initial_stop_loss(entry_price, session_low, atr)
                
                vol_20d_avg = cand['vol_20d'] if pd.notnull(cand['vol_20d']) else 500_000
                sizing = calculate_position_size(self.equity, entry_price, stop_loss, vol_20d_avg)
                
                if sizing['shares'] <= 0:
                    continue
                    
                pos = {
                    'symbol': sym,
                    'entry_date': d,
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'shares': sizing['shares'],
                    'allocated_capital': sizing['allocated_capital'],
                    'days_held': 1,
                    'is_swing': False,
                    'vol_ratio': vol_ratio,
                    'range_pos': range_pos,
                    'cand_row': cand
                }
                self.active_positions.append(pos)
                
            # --- 4. Layer 3: End-of-Day Persistence Check (15:15 IST) ---
            positions_to_keep = []
            for pos in self.active_positions:
                if pos['days_held'] == 1 and not pos['is_swing']:
                    # Check if position passes Layer 3
                    rp = pos['range_pos']
                    vr = pos['vol_ratio']
                    cand = pos['cand_row']
                    alpha = cand['daily_return'] - midcap_ret
                    
                    l3_eval = check_layer3_persistence(rp, vr, alpha)
                    
                    if l3_eval['qualifies_swing']:
                        pos['is_swing'] = True
                        pos['trailing_stop'] = cand['low']
                        positions_to_keep.append(pos)
                    else:
                        # Square off intraday at close with 0.2% slippage
                        exit_price = cand['close'] * 0.998
                        pnl = (exit_price - pos['entry_price']) * pos['shares']
                        self.equity += pnl
                        self.completed_trades.append({
                            'symbol': pos['symbol'],
                            'entry_date': pos['entry_date'],
                            'exit_date': d,
                            'entry_price': pos['entry_price'],
                            'exit_price': exit_price,
                            'shares': pos['shares'],
                            'pnl': pnl,
                            'pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                            'trade_type': 'INTRADAY',
                            'exit_reason': l3_eval['action']
                        })
                else:
                    positions_to_keep.append(pos)
                    
            self.active_positions = positions_to_keep
            self.daily_equity_curve.append({'date': d, 'equity': self.equity})
            
        return self._compute_performance()

    def _manage_swings(self, current_date: str, day_df: pd.DataFrame):
        retained = []
        for pos in self.active_positions:
            if not pos['is_swing']:
                retained.append(pos)
                continue
                
            sym = pos['symbol']
            sym_row = day_df[day_df['symbol'] == sym]
            if sym_row.empty:
                pos['days_held'] += 1
                retained.append(pos)
                continue
                
            row = sym_row.iloc[0]
            pos['days_held'] += 1
            curr_low = row['low']
            curr_high = row['high']
            curr_close = row['close']
            
            # 1. Stop loss hit?
            if curr_low <= pos['trailing_stop']:
                exit_price = pos['trailing_stop'] * 0.998
                pnl = (exit_price - pos['entry_price']) * pos['shares']
                self.equity += pnl
                self.completed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': current_date,
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'shares': pos['shares'],
                    'pnl': pnl,
                    'pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'trade_type': 'SWING',
                    'exit_reason': 'STOP_LOSS_HIT'
                })
                continue
                
            # 2. Max holding days reached?
            if pos['days_held'] >= cfg.SWING_MAX_HOLDING_DAYS:
                exit_price = curr_close * 0.998
                pnl = (exit_price - pos['entry_price']) * pos['shares']
                self.equity += pnl
                self.completed_trades.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': current_date,
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'shares': pos['shares'],
                    'pnl': pnl,
                    'pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'trade_type': 'SWING',
                    'exit_reason': 'MAX_HOLDING_DAYS'
                })
                continue
                
            # Ratchet trailing stop to previous day low
            pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
            retained.append(pos)
            
        self.active_positions = retained

    def _compute_performance(self) -> Dict[str, Any]:
        t_df = pd.DataFrame(self.completed_trades)
        eq_df = pd.DataFrame(self.daily_equity_curve)
        
        if t_df.empty:
            return {'total_trades': 0}
            
        wins = t_df[t_df['pnl'] > 0]
        losses = t_df[t_df['pnl'] <= 0]
        
        win_rate = (len(wins) / len(t_df)) * 100.0
        tot_profit = wins['pnl'].sum() if not wins.empty else 0.0
        tot_loss = abs(losses['pnl'].sum()) if not losses.empty else 1.0
        profit_factor = tot_profit / (tot_loss + 1e-6)
        
        eq_df['ret'] = eq_df['equity'].pct_change().fillna(0)
        sharpe = (eq_df['ret'].mean() / (eq_df['ret'].std() + 1e-9)) * np.sqrt(252)
        
        eq_df['peak'] = eq_df['equity'].cummax()
        eq_df['dd'] = (eq_df['equity'] - eq_df['peak']) / eq_df['peak']
        max_dd = abs(eq_df['dd'].min()) * 100.0
        
        net_return_pct = ((self.equity - self.initial_equity) / self.initial_equity) * 100.0
        
        return {
            'initial_equity': self.initial_equity,
            'final_equity': self.equity,
            'net_return_pct': net_return_pct,
            'total_trades': len(t_df),
            'win_rate_pct': win_rate,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'trades_df': t_df,
            'equity_df': eq_df
        }
