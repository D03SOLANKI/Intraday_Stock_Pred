import os
import sys
import pandas as pd
import numpy as np

def calculate_charges_and_net_pnl():
    csv_path = r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_detailed.csv'
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} trades from {csv_path}...")
    
    def compute_trade_costs(row):
        is_intra = (row['trade_type'] == 'INTRADAY')
        buy_val = row['shares'] * row['actual_entry_price']
        sell_val = row['shares'] * row['actual_exit_price']
        tot_turnover = buy_val + sell_val
        gross_pnl = sell_val - buy_val
        gross_pnl_pct = (gross_pnl / buy_val) * 100.0
        
        # 1. Brokerage:
        # Intraday: min(₹20, 0.03%) on buy leg + min(₹20, 0.03%) on sell leg
        # Delivery: ₹0 on buy & sell (Zerodha equity delivery standard) or flat ₹20/order
        if is_intra:
            brokerage = min(20.0, 0.0003 * buy_val) + min(20.0, 0.0003 * sell_val)
        else:
            brokerage = 0.0 # Free equity delivery standard
            
        # 2. Securities Transaction Tax (STT):
        # Intraday: 0.025% on SELL turnover only
        # Delivery: 0.10% on BOTH BUY and SELL turnover (total turnover)
        if is_intra:
            stt = 0.00025 * sell_val
        else:
            stt = 0.0010 * tot_turnover
            
        # 3. Exchange Transaction Charges (NSE):
        # 0.00297% on total turnover (Buy + Sell)
        exchange_charges = 0.0000297 * tot_turnover
        
        # 4. SEBI Turnover Charges:
        # ₹10 per crore = 0.0001% on total turnover
        sebi_charges = 0.000001 * tot_turnover
        
        # 5. Stamp Duty (Indian Stamp Act):
        # Charged on BUY turnover only:
        # Intraday: 0.003%
        # Delivery: 0.015%
        if is_intra:
            stamp_duty = 0.00003 * buy_val
        else:
            stamp_duty = 0.00015 * buy_val
            
        # 6. Goods and Services Tax (GST):
        # 18% on (Brokerage + Exchange Txn Charges + SEBI Charges)
        gst = 0.18 * (brokerage + exchange_charges + sebi_charges)
        
        # 7. Depository Participant (DP) Charges:
        # Charged per scrip per sell day on delivery trades:
        # ₹13.50 + 18% GST = ₹15.93 per delivery sell
        if is_intra:
            dp_charges = 0.0
        else:
            dp_charges = 15.93
            
        total_charges = (
            brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + dp_charges
        )
        
        net_pnl = gross_pnl - total_charges
        net_pnl_pct = (net_pnl / buy_val) * 100.0
        
        return pd.Series({
            'buy_turnover': buy_val,
            'sell_turnover': sell_val,
            'total_turnover': tot_turnover,
            'gross_pnl_inr': gross_pnl,
            'gross_pnl_pct': gross_pnl_pct,
            'brokerage_inr': brokerage,
            'stt_inr': stt,
            'exchange_charges_inr': exchange_charges,
            'sebi_charges_inr': sebi_charges,
            'stamp_duty_inr': stamp_duty,
            'gst_inr': gst,
            'dp_charges_inr': dp_charges,
            'total_charges_inr': total_charges,
            'net_pnl_inr': net_pnl,
            'net_pnl_pct': net_pnl_pct
        })
        
    costs_df = df.apply(compute_trade_costs, axis=1)
    
    # Merge with original dataframe
    out_df = pd.concat([df, costs_df], axis=1)
    
    # Save enriched CSV
    out_csv = r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_net_pnl.csv'
    out_df.to_csv(out_csv, index=False)
    print(f"Saved complete net P&L dataset to: {out_csv}")
    
    # Also overwrite the detailed CSV so it has all fields permanently
    detailed_csv = r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_detailed.csv'
    out_df.to_csv(detailed_csv, index=False)
    print(f"Updated {detailed_csv} with all net P&L and individual charge columns.")
    
    return out_df

if __name__ == '__main__':
    calculate_charges_and_net_pnl()
