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

def run_5year_backtest():
    print("Loading 5-year historical panel dataset...")
    all_df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_5year.pkl')
    top5_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\top5_daily_5year_enriched.csv')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    comp_map = dict(zip(n150_df['Symbol'], n150_df['Company Name']))
    top5_lookup = set(zip(top5_df['date'], top5_df['symbol']))
    top5_rank_map = {(r['date'], r['symbol']): int(r['rank']) for _, r in top5_df.iterrows()}
    
    unique_dates = sorted(all_df['date'].unique())
    print(f"Executing systematic strategy backtest across {len(unique_dates)} sessions (2021-2026)...")
    
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
        
        # 1. Manage Swings
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
            
            # Update extremes
            pos['highest_price'] = max(pos['highest_price'], curr_high)
            pos['lowest_price'] = min(pos['lowest_price'], curr_low)
            
            # Stop loss hit
            if curr_low <= pos['trailing_stop']:
                exit_price = pos['trailing_stop'] * 0.998
                pnl = (exit_price - pos['entry_price']) * pos['shares']
                equity += pnl
                
                is_t5 = (pos['entry_date'], sym) in top5_lookup
                t5_rank = top5_rank_map.get((pos['entry_date'], sym), None)
                mfe = ((pos['highest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                mae = ((pos['lowest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                
                dt, cr, se = synthesize_trade_causal_reason(
                    sym, pos['sector'], pos['cand_row'], is_t5, t5_rank, pos['vol_ratio'], pos['range_pos']
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
                    'gross_pnl_inr': pnl,
                    'gross_pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'highest_price_reached': pos['highest_price'],
                    'lowest_price_reached': pos['lowest_price'],
                    'mfe_pct': mfe,
                    'mae_pct': mae,
                    'actual_pct_gain_achieved': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'became_top_gainer': f"YES (Rank #{t5_rank} on NSE, +{pos['cand_row']['daily_return']:.2f}%)" if is_t5 else f"NO (+{pos['cand_row']['daily_return']:.2f}% daily gain)",
                    'price_movement_reason': cr,
                    'driver_type': dt,
                    'why_outperformed_sector': se,
                    'trade_type': 'SWING',
                    'exit_reason': 'STOP_LOSS_HIT'
                })
                continue
                
            # Max holding reached
            if pos['days_held'] >= cfg.SWING_MAX_HOLDING_DAYS:
                exit_price = curr_close * 0.998
                pnl = (exit_price - pos['entry_price']) * pos['shares']
                equity += pnl
                
                is_t5 = (pos['entry_date'], sym) in top5_lookup
                t5_rank = top5_rank_map.get((pos['entry_date'], sym), None)
                mfe = ((pos['highest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                mae = ((pos['lowest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                
                dt, cr, se = synthesize_trade_causal_reason(
                    sym, pos['sector'], pos['cand_row'], is_t5, t5_rank, pos['vol_ratio'], pos['range_pos']
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
                    'gross_pnl_inr': pnl,
                    'gross_pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'highest_price_reached': pos['highest_price'],
                    'lowest_price_reached': pos['lowest_price'],
                    'mfe_pct': mfe,
                    'mae_pct': mae,
                    'actual_pct_gain_achieved': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                    'became_top_gainer': f"YES (Rank #{t5_rank} on NSE, +{pos['cand_row']['daily_return']:.2f}%)" if is_t5 else f"NO (+{pos['cand_row']['daily_return']:.2f}% daily gain)",
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
        
        # Benchmark Headwind Protection (Skip new entries if midcap benchmark <= -0.50%)
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
                
        # 3. Layer 2 Intraday evaluation & CRMV Ranking
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
            sec_name = cand.get('sector', 'Mid-Cap Equities')
            
            selection_logic = (
                f"Layer 1: Pre-market base consolidation within ±3% of 20-DMA (dist_sma20: {cand['dist_sma20']:+.2f}%), "
                f"neutral RSI-14 ({cand['rsi_prev']:.1f}). "
                f"Layer 2: Clean positive opening gap of +{gap_pct*100:.2f}%, early volume surge ({vol_ratio:.2f}x 20d MA), "
                f"and upper-range accumulation (rng_pos: {range_pos:.2f}) passing negative-control volume trap exclusion."
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
            
        # 4. Layer 3 EOD Persistence (15:15 IST)
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
                    pnl = (exit_price - pos['entry_price']) * pos['shares']
                    equity += pnl
                    
                    is_t5 = (pos['entry_date'], pos['symbol']) in top5_lookup
                    t5_rank = top5_rank_map.get((pos['entry_date'], pos['symbol']), None)
                    mfe = ((pos['highest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                    mae = ((pos['lowest_price'] - pos['entry_price']) / pos['entry_price']) * 100.0
                    
                    dt, cr, se = synthesize_trade_causal_reason(
                        pos['symbol'], pos['sector'], cand, is_t5, t5_rank, pos['vol_ratio'], pos['range_pos']
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
                        'gross_pnl_inr': pnl,
                        'gross_pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                        'highest_price_reached': pos['highest_price'],
                        'lowest_price_reached': pos['lowest_price'],
                        'mfe_pct': mfe,
                        'mae_pct': mae,
                        'actual_pct_gain_achieved': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
                        'became_top_gainer': f"YES (Rank #{t5_rank} on NSE, +{cand['daily_return']:.2f}%)" if is_t5 else f"NO (+{cand['daily_return']:.2f}% daily gain)",
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
    print(f"\n5-Year Backtest completed. Total trades executed: {len(trades_df):,}")
    print(f"Starting Equity: INR {initial_equity:,.2f}")
    print(f"Ending Equity:   INR {equity:,.2f}")
    
    # Apply Statutory Charges
    print("Computing itemized statutory charges for all trades...")
    def compute_charges(row):
        is_intra = (row['trade_type'] == 'INTRADAY')
        buy_val = row['shares'] * row['actual_entry_price']
        sell_val = row['shares'] * row['actual_exit_price']
        tot_turnover = buy_val + sell_val
        
        # Brokerage
        brokerage = (min(20.0, 0.0003 * buy_val) + min(20.0, 0.0003 * sell_val)) if is_intra else 0.0
        # STT
        stt = (0.00025 * sell_val) if is_intra else (0.0010 * tot_turnover)
        # Exchange Txn Charges (0.00297%)
        exch = 0.0000297 * tot_turnover
        # SEBI (0.0001%)
        sebi = 0.000001 * tot_turnover
        # Stamp Duty (0.003% intraday buy / 0.015% delivery buy)
        stamp = (0.00003 * buy_val) if is_intra else (0.00015 * buy_val)
        # GST (18% on Brokerage + Exch + SEBI)
        gst = 0.18 * (brokerage + exch + sebi)
        # DP charges (₹15.93 per delivery sell)
        dp = 0.0 if is_intra else 15.93
        
        tot_charges = brokerage + stt + exch + sebi + stamp + gst + dp
        net_pnl = row['gross_pnl_inr'] - tot_charges
        net_pnl_pct = (net_pnl / buy_val) * 100.0
        
        return pd.Series({
            'buy_turnover': buy_val,
            'sell_turnover': sell_val,
            'total_turnover': tot_turnover,
            'brokerage_inr': brokerage,
            'stt_inr': stt,
            'exchange_charges_inr': exch,
            'sebi_charges_inr': sebi,
            'stamp_duty_inr': stamp,
            'gst_inr': gst,
            'dp_charges_inr': dp,
            'total_charges_inr': tot_charges,
            'net_pnl_inr': net_pnl,
            'net_pnl_pct': net_pnl_pct
        })
        
    charges_df = trades_df.apply(compute_charges, axis=1)
    full_trades_df = pd.concat([trades_df, charges_df], axis=1)
    
    # Merge exact daily universe rank
    full_trades_df = pd.merge(
        full_trades_df,
        all_df[['date', 'symbol', 'rank']].rename(columns={'rank': 'actual_universe_rank'}),
        left_on=['trading_date', 'symbol'],
        right_on=['date', 'symbol'],
        how='left'
    )
    if 'date' in full_trades_df.columns:
        full_trades_df = full_trades_df.drop(columns=['date'])
        
    full_trades_df['pred_rank_num'] = full_trades_df['predicted_rank'].str.extract(r'(\d+)').astype(int)
    full_trades_df['is_exact_rank1_hit'] = (full_trades_df['pred_rank_num'] == 1) & (full_trades_df['actual_universe_rank'] == 1)
    full_trades_df['is_top5_hit'] = full_trades_df['actual_universe_rank'] <= 5
    
    # Add Year column
    full_trades_df['year'] = pd.to_datetime(full_trades_df['trading_date']).dt.year
    
    out_csv = r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_5year_net_pnl.csv'
    full_trades_df.to_csv(out_csv, index=False)
    print(f"Saved complete 5-year trade dataset to: {out_csv}")
    
    # Save equity curve
    eq_df = pd.DataFrame(daily_equity_curve)
    eq_df.to_csv(r'e:\stock_predictor\stock_predictor\strategy_backtest_5year_equity_curve.csv', index=False)
    
    # Summary Metrics
    print("\n" + "="*70)
    print("5-YEAR SYSTEMATIC STRATEGY BACKTEST RESULTS (2021 - 2026)")
    print("="*70)
    tot_turnover = full_trades_df['total_turnover'].sum()
    gross_pnl = full_trades_df['gross_pnl_inr'].sum()
    tot_deductions = full_trades_df['total_charges_inr'].sum()
    net_pnl = full_trades_df['net_pnl_inr'].sum()
    
    gross_wins = full_trades_df[full_trades_df['gross_pnl_inr'] > 0]
    gross_losses = full_trades_df[full_trades_df['gross_pnl_inr'] <= 0]
    net_wins = full_trades_df[full_trades_df['net_pnl_inr'] > 0]
    net_losses = full_trades_df[full_trades_df['net_pnl_inr'] <= 0]
    
    gross_pf = gross_wins['gross_pnl_inr'].sum() / abs(gross_losses['gross_pnl_inr'].sum())
    net_pf = net_wins['net_pnl_inr'].sum() / abs(net_losses['net_pnl_inr'].sum())
    
    eq_df['ret'] = eq_df['equity'].pct_change().fillna(0)
    sharpe = (eq_df['ret'].mean() / (eq_df['ret'].std() + 1e-9)) * np.sqrt(252)
    eq_df['peak'] = eq_df['equity'].cummax()
    eq_df['dd'] = (eq_df['equity'] - eq_df['peak']) / eq_df['peak']
    max_dd = abs(eq_df['dd'].min()) * 100.0
    
    print(f"Total Trading Sessions:          {len(unique_dates)}")
    print(f"Total Executed Trades:           {len(full_trades_df):,}")
    print(f"Total Round-Trip Turnover:       INR {tot_turnover:,.2f}")
    print(f"Gross P&L:                       INR {gross_pnl:,.2f} (+{(gross_pnl/initial_equity)*100:.2f}%)")
    print(f"Total Statutory Deductions:      INR {tot_deductions:,.2f} ({(tot_deductions/gross_pnl)*100:.2f}% of gross)")
    print(f"Final Net P&L:                   INR {net_pnl:,.2f} (+{(net_pnl/initial_equity)*100:.2f}% Net Return)")
    print(f"Gross Win Rate:                  {(len(gross_wins)/len(full_trades_df))*100:.2f}%")
    print(f"Net Win Rate:                    {(len(net_wins)/len(full_trades_df))*100:.2f}%")
    print(f"Gross Profit Factor:             {gross_pf:.2f}")
    print(f"Net Profit Factor:               {net_pf:.2f}")
    print(f"Annualized Sharpe Ratio:         {sharpe:.2f}")
    print(f"Maximum Strategy Drawdown:       {max_dd:.2f}%")
    
    print("\n--- ANNUAL PERFORMANCE BREAKDOWN ---")
    annual = full_trades_df.groupby('year').agg(
        trades=('trade_id', 'count'),
        gross_pnl=('gross_pnl_inr', 'sum'),
        total_charges=('total_charges_inr', 'sum'),
        net_pnl=('net_pnl_inr', 'sum'),
        net_win_rate=('net_pnl_inr', lambda s: (s > 0).mean() * 100.0),
        top5_hits=('is_top5_hit', 'sum')
    )
    print(annual.to_string())
    
    return full_trades_df, annual

if __name__ == '__main__':
    run_5year_backtest()
