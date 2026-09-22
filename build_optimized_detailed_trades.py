import os
import sys
import math
import pandas as pd
import numpy as np

from config import strategy_config as cfg
from strategy.rules import (
    check_layer1_premarket,
    check_layer2_intraday,
    check_volume_trap_exclusion,
    check_layer3_persistence
)
from strategy.position_sizer import calculate_initial_stop_loss, calculate_position_size
from build_detailed_trades_dataset import synthesize_trade_causal_reason

def run_optimized_detailed_backtest():
    print("Loading 5-year historical panel dataset...")
    all_df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    comp_map = dict(zip(n150_df['Symbol'], n150_df['Company Name']))
    sector_map = dict(zip(n150_df['Symbol'], n150_df['Sector'])) if 'Sector' in n150_df.columns else {}
    
    # Pre-calculate actual universe rank for all stock-days
    print("Computing actual daily universe rank for all 169,920 stock-days...")
    all_df['actual_universe_rank'] = all_df.groupby('date')['daily_return'].rank(ascending=False, method='min').astype(int)
    
    rank_lookup = dict(zip(zip(all_df['date'], all_df['symbol']), all_df['actual_universe_rank']))
    ret_lookup = dict(zip(zip(all_df['date'], all_df['symbol']), all_df['daily_return']))
    
    unique_dates = sorted(all_df['date'].unique())
    print(f"Executing systematic backtest across {len(unique_dates)} sessions under Optimized Production Strategy...")
    
    equity = cfg.PORTFOLIO_INITIAL_EQUITY
    initial_equity = cfg.PORTFOLIO_INITIAL_EQUITY
    active_positions = []
    completed_trades = []
    daily_equity_curve = []
    
    trade_id_counter = 1
    
    for d_idx, d in enumerate(unique_dates):
        day_df = all_df[all_df['date'] == d]
        if day_df.empty:
            continue
            
        midcap_ret = day_df['midcap_ret'].iloc[0] if 'midcap_ret' in day_df.columns else 0.0
        
        # 1. Manage Active Swings
        retained = []
        for pos in active_positions:
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
            
            pos['highest_price'] = max(pos['highest_price'], curr_high)
            pos['lowest_price'] = min(pos['lowest_price'], curr_low)
            
            # Stop loss hit
            if curr_low <= pos['trailing_stop']:
                exit_price = pos['trailing_stop'] * 0.998
                gross_pnl = (exit_price - pos['entry_price']) * pos['shares']
                equity += gross_pnl
                
                act_rank = rank_lookup.get((pos['entry_date'], sym), 75)
                act_ret = ret_lookup.get((pos['entry_date'], sym), 0.0)
                is_t5 = (act_rank <= 5)
                
                mfe = ((pos['highest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                mae = ((pos['lowest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                
                dt, cr, se = synthesize_trade_causal_reason(
                    sym, pos['sector'], pos['cand_row'], is_t5, act_rank, pos['vol_ratio'], pos['range_pos']
                )
                
                completed_trades.append({
                    'trade_id': pos['trade_id'],
                    'trading_date': pos['entry_date'],
                    'symbol': sym,
                    'company_name': pos['company_name'],
                    'sector': pos['sector'],
                    'selection_reason': pos['selection_reason'],
                    'prediction_date': pos['prediction_date'],
                    'predicted_rank': pos['predicted_rank'],
                    'entry_price': pos['entry_price'],
                    'stop_loss': pos['stop_loss'],
                    'take_profit': pos['take_profit'],
                    'actual_entry_price': pos['entry_price'],
                    'actual_exit_price': exit_price,
                    'exit_date': d,
                    'exit_time': '09:35 IST (Trailing Stop Loss Triggered)',
                    'shares': pos['shares'],
                    'capital_allocated': pos['allocated_capital'],
                    'holding_period': f"{pos['days_held']} Days (Swing)",
                    'sl_or_tp_hit': 'SL HIT (Trailing Stop Triggered)',
                    'gross_pnl_inr': gross_pnl,
                    'gross_pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'highest_price_reached': pos['highest_price'],
                    'lowest_price_reached': pos['lowest_price'],
                    'mfe_pct': mfe,
                    'mae_pct': mae,
                    'actual_pct_gain_achieved': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'actual_universe_rank': act_rank,
                    'became_top_gainer': f"YES (Rank #{act_rank} on NSE, +{act_ret:.2f}%)" if is_t5 else f"NO (Rank #{act_rank}, +{act_ret:.2f}%)",
                    'price_movement_reason': cr,
                    'driver_type': dt,
                    'why_outperformed_sector': se,
                    'trade_type': 'SWING',
                    'exit_reason': 'STOP_LOSS_HIT'
                })
                continue
                
            # Max holding days reached
            if pos['days_held'] >= cfg.SWING_MAX_HOLDING_DAYS:
                exit_price = curr_close * 0.998
                gross_pnl = (exit_price - pos['entry_price']) * pos['shares']
                equity += gross_pnl
                
                act_rank = rank_lookup.get((pos['entry_date'], sym), 75)
                act_ret = ret_lookup.get((pos['entry_date'], sym), 0.0)
                is_t5 = (act_rank <= 5)
                
                mfe = ((pos['highest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                mae = ((pos['lowest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                
                dt, cr, se = synthesize_trade_causal_reason(
                    sym, pos['sector'], pos['cand_row'], is_t5, act_rank, pos['vol_ratio'], pos['range_pos']
                )
                
                tp_hit = "TP REACHED (Peak > +5%)" if pos['highest_price'] >= pos['take_profit'] else "TIME EXIT (Max 5 Days)"
                
                completed_trades.append({
                    'trade_id': pos['trade_id'],
                    'trading_date': pos['entry_date'],
                    'symbol': sym,
                    'company_name': pos['company_name'],
                    'sector': pos['sector'],
                    'selection_reason': pos['selection_reason'],
                    'prediction_date': pos['prediction_date'],
                    'predicted_rank': pos['predicted_rank'],
                    'entry_price': pos['entry_price'],
                    'stop_loss': pos['stop_loss'],
                    'take_profit': pos['take_profit'],
                    'actual_entry_price': pos['entry_price'],
                    'actual_exit_price': exit_price,
                    'exit_date': d,
                    'exit_time': '15:20 IST (Max 5-Day Holding Expiration)',
                    'shares': pos['shares'],
                    'capital_allocated': pos['allocated_capital'],
                    'holding_period': f"{pos['days_held']} Days (Swing)",
                    'sl_or_tp_hit': tp_hit,
                    'gross_pnl_inr': gross_pnl,
                    'gross_pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'highest_price_reached': pos['highest_price'],
                    'lowest_price_reached': pos['lowest_price'],
                    'mfe_pct': mfe,
                    'mae_pct': mae,
                    'actual_pct_gain_achieved': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'actual_universe_rank': act_rank,
                    'became_top_gainer': f"YES (Rank #{act_rank} on NSE, +{act_ret:.2f}%)" if is_t5 else f"NO (Rank #{act_rank}, +{act_ret:.2f}%)",
                    'price_movement_reason': cr,
                    'driver_type': dt,
                    'why_outperformed_sector': se,
                    'trade_type': 'SWING',
                    'exit_reason': 'MAX_HOLDING_DAYS'
                })
                continue
                
            pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
            retained.append(pos)
            
        active_positions = retained
        
        # Benchmark Headwind Protection: Skip new long entries if Midcap index opens down <= -0.50%
        headwind_limit = getattr(cfg, 'MIDCAP_HEADWIND_MIN_PCT', -0.005)
        if midcap_ret < headwind_limit:
            daily_equity_curve.append({'date': d, 'equity': equity})
            continue
            
        # 2. Layer 1 Pre-market screening
        l1_candidates = []
        for _, row in day_df.iterrows():
            dist_sma = abs(row['dist_sma20']) / 100.0 if pd.notnull(row['dist_sma20']) else 0.5
            rsi_prev = row['rsi_prev'] if pd.notnull(row['rsi_prev']) else 50.0
            if dist_sma <= cfg.COILING_DMA_PROXIMITY_PCT and (cfg.RSI_14_MIN <= rsi_prev <= cfg.RSI_14_MAX):
                l1_candidates.append(row)
                
        # 3. Layer 2 Intraday filtering & CRMV Ranking
        l2_passing = []
        for cand in l1_candidates:
            sym = cand['symbol']
            if any(p['symbol'] == sym for p in active_positions):
                continue
                
            prev_close = cand['prev_close']
            open_price = cand['open']
            gap_pct = (open_price - prev_close) / prev_close
            
            if not (cfg.GAP_MIN_PCT <= gap_pct <= cfg.GAP_MAX_PCT):
                continue
                
            # Volume expansion check (Calibrated to 1.60x)
            vol_ratio = cand['vol_ratio'] if pd.notnull(cand['vol_ratio']) else 1.0
            vol_threshold = getattr(cfg, 'VOL_RATIO_MIN_L2', 1.60)
            if vol_ratio < vol_threshold:
                continue
                
            range_pos = cand['rng_pos'] if pd.notnull(cand['rng_pos']) else 0.5
            if check_volume_trap_exclusion(vol_ratio, range_pos):
                continue
                
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

        cand_rank_counter = 1
        for cand in ordered_candidates:
            if len(active_positions) >= cfg.MAX_CONCURRENT_POSITIONS:
                break
                
            sym = cand['symbol']
            if any(p['symbol'] == sym for p in active_positions):
                continue
                
            prev_close = cand['prev_close']
            open_price = cand['open']
            gap_pct = (open_price - prev_close) / prev_close
            vol_ratio = cand['vol_ratio'] if pd.notnull(cand['vol_ratio']) else 1.0
            range_pos = cand['rng_pos'] if pd.notnull(cand['rng_pos']) else 0.5
            
            entry_price = open_price * 1.003
            session_low = cand['low']
            session_high = cand['high']
            atr = prev_close * 0.02
            stop_loss = calculate_initial_stop_loss(entry_price, session_low, atr)
            take_profit = entry_price * 1.05
            
            vol_20d_avg = cand['vol_20d'] if pd.notnull(cand['vol_20d']) else 500_000
            sizing = calculate_position_size(equity, entry_price, stop_loss, vol_20d_avg)
            
            if sizing['shares'] <= 0:
                continue
                
            comp_name = comp_map.get(sym, cand.get('company', sym))
            sec_name = sector_map.get(sym, cand.get('sector', 'Mid-Cap Equities'))
            
            selection_logic = (
                f"Layer 1: Pre-market base consolidation within ±3% of 20-DMA (dist_sma20: {cand['dist_sma20']:+.2f}%), "
                f"neutral RSI-14 ({cand['rsi_prev']:.1f}). "
                f"Layer 2: Clean positive opening gap of +{gap_pct*100:.2f}%, institutional volume surge ({vol_ratio:.2f}x 20d MA), "
                f"upper-range accumulation (rng_pos: {range_pos:.2f}). "
                f"CRMV Ranking: Selected as Rank #{cand_rank_counter} by Composite Relative Momentum & Velocity Score."
            )
            
            pos = {
                'trade_id': trade_id_counter,
                'symbol': sym,
                'company_name': comp_name,
                'sector': sec_name,
                'entry_date': d,
                'prediction_date': f"{d} (08:45 IST)",
                'predicted_rank': f"Rank #{cand_rank_counter}",
                'selection_reason': selection_logic,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'shares': sizing['shares'],
                'allocated_capital': sizing['allocated_capital'],
                'days_held': 1,
                'is_swing': False,
                'highest_price': session_high,
                'lowest_price': min(session_low, entry_price),
                'vol_ratio': vol_ratio,
                'range_pos': range_pos,
                'cand_row': cand
            }
            active_positions.append(pos)
            trade_id_counter += 1
            cand_rank_counter += 1
            
        # 4. Layer 3 EOD Persistence Check (15:15 IST)
        positions_to_keep = []
        for pos in active_positions:
            if pos['days_held'] == 1 and not pos['is_swing']:
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
                    exit_price = cand['close'] * 0.998
                    gross_pnl = (exit_price - pos['entry_price']) * pos['shares']
                    equity += gross_pnl
                    
                    act_rank = rank_lookup.get((pos['entry_date'], pos['symbol']), 75)
                    act_ret = ret_lookup.get((pos['entry_date'], pos['symbol']), 0.0)
                    is_t5 = (act_rank <= 5)
                    
                    mfe = ((pos['highest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                    mae = ((pos['lowest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                    
                    dt, cr, se = synthesize_trade_causal_reason(
                        pos['symbol'], pos['sector'], cand, is_t5, act_rank, pos['vol_ratio'], pos['range_pos']
                    )
                    
                    tp_status = "TP TARGET EXCEEDED / INTRADAY CLOSE" if pos['highest_price'] >= pos['take_profit'] else "SQUARE OFF INTRADAY"
                    
                    completed_trades.append({
                        'trade_id': pos['trade_id'],
                        'trading_date': pos['entry_date'],
                        'symbol': pos['symbol'],
                        'company_name': pos['company_name'],
                        'sector': pos['sector'],
                        'selection_reason': pos['selection_reason'],
                        'prediction_date': pos['prediction_date'],
                        'predicted_rank': pos['predicted_rank'],
                        'entry_price': pos['entry_price'],
                        'stop_loss': pos['stop_loss'],
                        'take_profit': pos['take_profit'],
                        'actual_entry_price': pos['entry_price'],
                        'actual_exit_price': exit_price,
                        'exit_date': d,
                        'exit_time': '15:20 IST (Layer 3 Square-Off)',
                        'shares': pos['shares'],
                        'capital_allocated': pos['allocated_capital'],
                        'holding_period': '1 Day (Intraday)',
                        'sl_or_tp_hit': tp_status,
                        'gross_pnl_inr': gross_pnl,
                        'gross_pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                        'highest_price_reached': pos['highest_price'],
                        'lowest_price_reached': pos['lowest_price'],
                        'mfe_pct': mfe,
                        'mae_pct': mae,
                        'actual_pct_gain_achieved': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                        'actual_universe_rank': act_rank,
                        'became_top_gainer': f"YES (Rank #{act_rank} on NSE, +{act_ret:.2f}%)" if is_t5 else f"NO (Rank #{act_rank}, +{act_ret:.2f}%)",
                        'price_movement_reason': cr,
                        'driver_type': dt,
                        'why_outperformed_sector': se,
                        'trade_type': 'INTRADAY',
                        'exit_reason': l3_eval['action']
                    })
            else:
                positions_to_keep.append(pos)
                
        active_positions = positions_to_keep
        daily_equity_curve.append({'date': d, 'equity': equity})
        
    trades_df = pd.DataFrame(completed_trades)
    print(f"Optimized backtest complete. Total trades: {len(trades_df):,}")
    print(f"Final Equity: INR {equity:,.2f}")
    
    # Statutory charges calculation
    print("Computing statutory charges (STT, Exchange, SEBI, GST, Stamp Duty, DP) for every trade...")
    def compute_trade_costs(row):
        is_intra = (row['trade_type'] == 'INTRADAY')
        buy_val = row['shares'] * row['actual_entry_price']
        sell_val = row['shares'] * row['actual_exit_price']
        tot_turnover = buy_val + sell_val
        gross_pnl = row['gross_pnl_inr']
        
        # 1. Brokerage
        if is_intra:
            brokerage = min(20.0, 0.0003 * buy_val) + min(20.0, 0.0003 * sell_val)
        else:
            brokerage = 0.0
            
        # 2. STT
        if is_intra:
            stt = 0.00025 * sell_val
        else:
            stt = 0.0010 * tot_turnover
            
        # 3. Exchange charges (0.00297%)
        exchange_charges = 0.0000297 * tot_turnover
        
        # 4. SEBI charges (0.0001%)
        sebi_charges = 0.000001 * tot_turnover
        
        # 5. Stamp duty
        if is_intra:
            stamp_duty = 0.00003 * buy_val
        else:
            stamp_duty = 0.00015 * buy_val
            
        # 6. GST
        gst = 0.18 * (brokerage + exchange_charges + sebi_charges)
        
        # 7. DP charges
        if is_intra:
            dp_charges = 0.0
        else:
            dp_charges = 15.93
            
        tot_charges = brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + dp_charges
        net_pnl = gross_pnl - tot_charges
        net_pnl_pct = (net_pnl / buy_val) * 100.0
        
        return pd.Series({
            'buy_turnover': buy_val,
            'sell_turnover': sell_val,
            'total_turnover': tot_turnover,
            'brokerage_inr': brokerage,
            'stt_inr': stt,
            'exchange_charges_inr': exchange_charges,
            'sebi_charges_inr': sebi_charges,
            'stamp_duty_inr': stamp_duty,
            'gst_inr': gst,
            'dp_charges_inr': dp_charges,
            'total_charges_inr': tot_charges,
            'net_pnl_inr': net_pnl,
            'net_pnl_pct': net_pnl_pct
        })

    charges_df = trades_df.apply(compute_trade_costs, axis=1)
    full_df = pd.concat([trades_df, charges_df], axis=1)
    
    csv_path = r'e:\stock_predictor\stock_predictor\optimized_strategy_trades_5year_detailed.csv'
    pkl_path = r'e:\stock_predictor\stock_predictor\optimized_strategy_trades_5year_detailed.pkl'
    full_df.to_csv(csv_path, index=False)
    full_df.to_pickle(pkl_path)
    print(f"Saved optimized trades dataset to: {csv_path} and {pkl_path}")
    
    return full_df, equity, daily_equity_curve

if __name__ == '__main__':
    run_optimized_detailed_backtest()
