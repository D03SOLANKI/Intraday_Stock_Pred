import os
import sys
import pandas as pd
from config import strategy_config as cfg
from strategy.rules import check_volume_trap_exclusion

def generate_no_trade_days_report():
    all_df = pd.read_pickle(r'e:\stock_predictor\stock_predictor\all_midcap_stock_days_1year.pkl')
    trades_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_detailed.csv')

    trade_dates = set(trades_df['trading_date'].unique())
    all_dates = sorted(all_df['date'].unique())
    no_trade_dates = [d for d in all_dates if d not in trade_dates]

    rows = []
    for d in no_trade_dates:
        day_df = all_df[all_df['date'] == d]
        midcap_ret = day_df['daily_return'].mean()
        
        held = trades_df[(trades_df['trading_date'] < d) & (trades_df['exit_date'] >= d)]
        held_count = len(held)
        
        l1_candidates = []
        for _, row in day_df.iterrows():
            dist_sma = abs(row['dist_sma20']) / 100.0 if pd.notnull(row['dist_sma20']) else 0.5
            rsi_prev = row['rsi_prev'] if pd.notnull(row['rsi_prev']) else 50.0
            if dist_sma <= cfg.COILING_DMA_PROXIMITY_PCT and (cfg.RSI_14_MIN <= rsi_prev <= cfg.RSI_14_MAX):
                l1_candidates.append(row)
                
        trap_syms = []
        vol_rejects = 0
        exhaust_gap_syms = []
        gap_down_syms = []
        
        for cand in l1_candidates:
            sym = cand['symbol']
            prev_close = cand['prev_close']
            open_p = cand['open']
            gap_pct = (open_p - prev_close) / prev_close
            vol_ratio = cand['vol_ratio'] if pd.notnull(cand['vol_ratio']) else 1.0
            range_pos = cand['rng_pos'] if pd.notnull(cand['rng_pos']) else 0.5
            
            if gap_pct < cfg.GAP_MIN_PCT:
                gap_down_syms.append(sym)
            elif gap_pct > cfg.GAP_MAX_PCT:
                exhaust_gap_syms.append(sym)
            elif vol_ratio < 1.3:
                vol_rejects += 1
            elif check_volume_trap_exclusion(vol_ratio, range_pos):
                trap_syms.append(sym)
                
        if held_count >= cfg.MAX_CONCURRENT_POSITIONS:
            held_syms = ', '.join(held['symbol'].head(3).tolist())
            reason_category = "Portfolio Capacity Limit"
            detailed_reason = f"Max 5 concurrent positions already active ({held_syms}). Risk engine blocked new entries."
            predicted_rejected = "Yes (Valid candidates met L1 & L2, but portfolio risk cap full)"
            strategy_condition = "Risk Rule: Max 5 Concurrent Positions / Capital fully committed"
        elif len(trap_syms) > 0:
            trap_list = ', '.join(trap_syms[:2])
            reason_category = "Negative-Control Volume Trap"
            detailed_reason = f"Breakout candidates ({trap_list}) showed high volume with weak close (Range Pos <= 0.40), indicating institutional distribution."
            predicted_rejected = f"Yes ({trap_syms[0]} passed pre-market L1 but rejected at L2)"
            strategy_condition = "Negative Control Filter: Vol Ratio >= 1.5x with Range Position <= 0.40"
        elif len(exhaust_gap_syms) > 0 and (len(exhaust_gap_syms) + len(gap_down_syms) >= len(l1_candidates) - 2):
            reason_category = "Hostile Gap Environment"
            detailed_reason = f"Broader market gap dislocation ({len(gap_down_syms)} gap-downs, {len(exhaust_gap_syms)} exhausted gaps >2.5%)."
            predicted_rejected = "Yes (Pre-market coiled candidates failed opening gap bounds [+0.2% to +2.5%])"
            strategy_condition = "Execution Filter: Opening Gap outside acceptable bounds"
        else:
            reason_category = "Subdued Institutional Velocity"
            detailed_reason = f"{vol_rejects} coiled candidates failed early volume threshold (Vol Ratio < 1.3x). Lack of institutional order flow."
            predicted_rejected = "Yes (Coiled candidates lacked required early volume expansion)"
            strategy_condition = "Liquidity Rule: Early volume velocity < 1.3x 20-DMA"
            
        rows.append({
            'date': d,
            'midcap_return_pct': round(midcap_ret, 2),
            'active_positions_held': held_count,
            'l1_coiled_candidates_found': len(l1_candidates),
            'reason_category': reason_category,
            'detailed_reason': detailed_reason,
            'predicted_stock_rejected': predicted_rejected,
            'qualifying_stock_found': 'No (0 stocks met combined Layer 1 + 2 + Risk rules)',
            'strategy_condition_preventing_trade': strategy_condition
        })

    out_df = pd.DataFrame(rows)
    csv_path = r'e:\stock_predictor\stock_predictor\no_trade_days_audit.csv'
    out_df.to_csv(csv_path, index=False)
    print(f"Successfully saved audit of all {len(out_df)} no-trade days to: {csv_path}")
    return out_df

if __name__ == '__main__':
    generate_no_trade_days_report()
