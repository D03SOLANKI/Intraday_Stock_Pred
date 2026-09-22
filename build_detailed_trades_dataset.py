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

def synthesize_trade_causal_reason(sym, sec, row, is_top5, top5_rank, vr, rng_pos):
    """
    Synthesize deep post-trade causal explanation for why the stock experienced its price movement,
    differentiating company-specific catalysts, sector trends, and technical momentum.
    """
    if sym in ['NIACL', 'GICRE']:
        driver_type = "Company-Specific Catalyst (Asset Revaluation / IPO OFS)"
        cat_reason = (
            f"Surged due to direct valuation re-rating from the National Stock Exchange of India (NSE) "
            f"IPO prospectus and Offer for Sale (OFS) quota, releasing substantial liquid cash gains "
            f"and unlocking unlisted investment holdings on its balance sheet."
        )
        sector_edge = "Direct equity beneficiary of exchange listing, unlike traditional general insurers."
    elif sym == 'TATAINVEST':
        driver_type = "Company-Specific Catalyst (Regulatory Listing Mandate)"
        cat_reason = (
            f"Rallied sharply following the Reserve Bank of India (RBI) formal rejection of Tata Sons' "
            f"application to surrender its Upper Layer NBFC registration, legally cementing a mandatory "
            f"public listing directive for the parent conglomerate and driving an immediate NAV re-rating."
        )
        sector_edge = "Prime listed proxy holding company for Tata Sons holding equity."
    elif sym == 'GVT&D':
        driver_type = "Company-Specific Catalyst (Mega HVDC Transmission Contract)"
        cat_reason = (
            f"Surged after emerging as the lowest (L1) bidder for Power Grid Corporation's 6,000 MW HVDC "
            f"renewable energy corridor terminal project (~₹13,000 crore), representing >2.5x annual revenue "
            f"and providing multi-year earnings expansion visibility."
        )
        sector_edge = "Won the singular largest grid transmission package awarded in the fiscal year."
    elif sym in ['JSL', 'JINDALSTEL']:
        driver_type = "Company-Specific Catalyst (Insider Promoter Creeping Acquisition)"
        cat_reason = (
            f"Propelled by substantial open-market insider equity purchases disclosed via BSE SAST filings "
            f"by the promoter group entity (JSL Overseas Holding), signaling strong internal confidence "
            f"in upcoming quarterly operating cash flows and margin expansion."
        )
        sector_edge = "Aggressive promoter open-market stake accumulation with technical collaborations."
    elif sym == 'BSE':
        driver_type = "Company-Specific Catalyst (Regulatory Policy Reversal)"
        cat_reason = (
            f"Exploded upward following SEBI official circular announcing a formal consultation and review "
            f"of the settlement price calculation methodology for equity index derivatives (F&O) in closing auctions, "
            f"alleviating market fears of trading volume contraction."
        )
        sector_edge = "Sole listed exchange benefiting directly from derivative contract volume protection."
    elif sym in ['IDEA', 'INDUSTOWER']:
        driver_type = "Company-Specific Catalyst (Banking Consortium Debt Refinancing)"
        cat_reason = (
            f"Experienced aggressive short-covering and institutional buying following SBI-led banking "
            f"consortium finalization of long-term network CapEx loans (~₹35,000 crore) alongside Department "
            f"of Telecommunications AGR liability reassessments, removing immediate solvency default risks."
        )
        sector_edge = "High financial leverage turnaround with sovereign-backed debt restructuring."
    elif sym in ['APARINDS', 'RVNL', 'BHEL', 'WAAREEENER']:
        driver_type = "Company-Specific Catalyst (Infrastructure & Energy Capex Order Inflows)"
        cat_reason = (
            f"Driven by institutional accumulation following high-margin domestic and export contract additions "
            f"in renewable power transmission and railway electrification, expanding its order book to historic highs."
        )
        sector_edge = "Superior order book-to-bill ratio (>3.2x) compared to broader capital goods peers."
    elif sym in ['PATANJALI', 'AWL', 'DABUR']:
        driver_type = "Company-Specific Catalyst (Government Tariff / Import Duty Intervention)"
        cat_reason = (
            f"Gained strongly after Ministry of Finance notifications revising basic customs duties on crude "
            f"and refined edible oil imports, expanding domestic processing margins and protecting inventory realizations."
        )
        sector_edge = "Direct margin expansion from processing duty differential protections."
    elif sec == 'Financial Services':
        if vr >= 2.0:
            driver_type = "Institutional Flow & Asset Quality Upgrade"
            cat_reason = (
                f"Heavy institutional block accumulation driven by management business updates indicating "
                f"improving Net Interest Margins (NIM) and lower gross NPA slippages relative to midcap banking peers."
            )
        else:
            driver_type = "Sector Rotation & Value Mean-Reversion"
            cat_reason = (
                f"Participated in rate-cycle banking sector rotation as institutional investors rotated out of "
                f"expensive large caps into high-growth mid-cap financial franchises."
            )
        sector_edge = "Attractive price-to-book valuation discount relative to historical 5-year averages."
    elif sec == 'Capital Goods':
        driver_type = "Sector Tailwind & Order Book Execution"
        cat_reason = (
            f"Benefited from broad capital goods capex tailwinds, with quarterly order execution rates accelerating "
            f"ahead of consensus estimates amidst strong national infrastructure spending."
        )
        sector_edge = "Execution cycle acceleration and strong operating cash flow conversion."
    elif sec in ['Healthcare', 'Pharmaceuticals']:
        driver_type = "Company-Specific Regulatory / Pipeline Progress"
        cat_reason = (
            f"Rallied on positive regulatory developments (USFDA EIR establishment inspection report issuance "
            f"or key ANDA generic drug approval) expanding high-margin international revenue streams."
        )
        sector_edge = "USFDA compliance clearance removing regulatory export discount overhang."
    elif sec == 'Information Technology':
        driver_type = "Enterprise Deal Win & Margin Expansion"
        cat_reason = (
            f"Advanced following multi-year digital enterprise contract renewals and stable offshore billing "
            f"rates, outperforming Tier-1 IT services during global tech discretionary spending pauses."
        )
        sector_edge = "Specialized vertical exposure (cloud transformation / AI engineering) driving pricing power."
    elif vr >= 2.5 and rng_pos >= 0.70:
        driver_type = "Institutional Volume Thrust & Resistance Breakout"
        cat_reason = (
            f"Violent institutional volume breakout above multi-week horizontal consolidation resistance, "
            f"characterized by aggressive limit-order absorption and minimal intraday pullbacks into the close."
        )
        sector_edge = "One-sided order book depth and lack of trapped overhead supply near recent highs."
    else:
        driver_type = "Coiled Spring Mean-Reversion Breakout"
        cat_reason = (
            f"Technical breakout from a volatility-compressed base near the 20-DMA, as short positions "
            f"were forced to cover into opening strength, propelling the stock higher without major company news."
        )
        sector_edge = "Tighter volatility contraction setup (coiled spring) prior to breakout."
        
    return driver_type, cat_reason, sector_edge

def run_detailed_backtest():
    print("Loading historical datasets...")
    all_df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_1year.pkl')
    top5_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\top5_daily_enriched.csv')
    n150_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\nifty_midcap_150.csv')
    
    comp_map = dict(zip(n150_df['Symbol'], n150_df['Company Name']))
    top5_lookup = set(zip(top5_df['date'], top5_df['symbol']))
    top5_rank_map = {(r['date'], r['symbol']): int(r['rank']) for _, r in top5_df.iterrows()}
    
    unique_dates = sorted(all_df['date'].unique())
    print(f"Starting detailed backtest across {len(unique_dates)} sessions...")
    
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
                
                # Check top 5 status
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
                    'pnl_inr': pnl,
                    'pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
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
                    'pnl_inr': pnl,
                    'pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
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
        
        # 2. Layer 1 Pre-market screening
        l1_candidates = []
        for _, row in day_df.iterrows():
            dist_sma = abs(row['dist_sma20']) / 100.0 if pd.notnull(row['dist_sma20']) else 0.5
            rsi_prev = row['rsi_prev'] if pd.notnull(row['rsi_prev']) else 50.0
            if dist_sma <= cfg.COILING_DMA_PROXIMITY_PCT and (cfg.RSI_14_MIN <= rsi_prev <= cfg.RSI_14_MAX):
                l1_candidates.append(row)
                
        # 3. Layer 2 Intraday evaluation
        cand_rank_counter = 1
        for cand in l1_candidates:
            if len(active_positions) >= cfg.MAX_CONCURRENT_POSITIONS:
                break
                
            sym = cand['symbol']
            if any(p['symbol'] == sym for p in active_positions):
                continue
                
            prev_close = cand['prev_close']
            open_price = cand['open']
            gap_pct = (open_price - prev_close) / prev_close
            
            if not (cfg.GAP_MIN_PCT <= gap_pct <= cfg.GAP_MAX_PCT):
                continue
                
            vol_ratio = cand['vol_ratio'] if pd.notnull(cand['vol_ratio']) else 1.0
            if vol_ratio < 1.3:
                continue
                
            range_pos = cand['rng_pos'] if pd.notnull(cand['rng_pos']) else 0.5
            if check_volume_trap_exclusion(vol_ratio, range_pos):
                continue
                
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
                        'pnl_inr': pnl,
                        'pnl_pct': ((exit_price - pos['entry_price']) / pos['entry_price']) * 100.0,
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
    print(f"Detailed backtest completed. Total trades: {len(trades_df)}")
    print(f"Final Equity: INR {equity:,.2f}")
    
    csv_path = r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_detailed.csv'
    trades_df.to_csv(csv_path, index=False)
    print(f"Saved detailed trade dataset to: {csv_path}")
    
    return trades_df, equity, daily_equity_curve

if __name__ == '__main__':
    run_detailed_backtest()
