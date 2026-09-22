import os
import sys
import pandas as pd
import numpy as np

def generate_markdown_ranking():
    daily_stats = pd.read_csv(r'e:\stock_predictor\stock_predictor\daily_trading_activity_ranked.csv')
    trades = pd.read_csv(r'e:\stock_predictor\stock_predictor\daily_trades_ranked_by_activity.csv')
    
    md_path = r'C:\Users\DEV SOLANKI\.gemini\antigravity\brain\1039690e-8900-4776-bdf6-ba1ff6093472\daily_trading_activity_ranking.md'
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# Daily Trading Activity Ranking: All Backtest Days Ranked by Trades per Day\n\n")
        f.write("**Total Active Trading Sessions:** 209 Days  \n")
        f.write("**Total Systematic Trades:** 602 Executed Positions  \n")
        f.write("**Total Net Profit:** +₹15,147,937.12 (Net Return: +151.48%)  \n")
        f.write("**Master Word Document:** [MidCap_Top_Gainer_Daily_Trade_Activity_Ranking.docx](file:///e:/stock_predictor/stock_predictor/MidCap_Top_Gainer_Daily_Trade_Activity_Ranking.docx)  \n")
        f.write("**Day-Level Summary CSV:** [daily_trading_activity_ranked.csv](file:///e:/stock_predictor/stock_predictor/daily_trading_activity_ranked.csv)  \n")
        f.write("**Trade-Level Detail CSV:** [daily_trades_ranked_by_activity.csv](file:///e:/stock_predictor/stock_predictor/daily_trades_ranked_by_activity.csv)  \n\n")
        f.write("---\n\n")
        
        f.write("## 1. Trading Activity Tier Distribution\n\n")
        f.write("| Activity Tier | Trades / Day | Days Count | % of Days | Total Trades | Total Capital Deployed (₹) | Net P&L (₹) | Win Rate |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        
        for tc in [5, 4, 3, 2, 1]:
            sub_d = daily_stats[daily_stats['trade_count'] == tc]
            sub_t = trades[trades['trade_count'] == tc]
            wr = (sub_t['net_pnl_inr'] > 0).mean() * 100.0
            f.write(f"| **Tier {6-tc}: {'Max Capacity' if tc==5 else 'Active Flow'}** | **{tc} trades** | {len(sub_d)} days | {(len(sub_d)/len(daily_stats))*100:.1f}% | {len(sub_d)*tc} trades | ₹{sub_d['total_capital'].sum():,.2f} | **+₹{sub_d['net_pnl'].sum():,.2f}** | {wr:.1f}% |\n")
            
        f.write("\n---\n\n")
        f.write("## 2. Complete Ranking of All 209 Trading Days (Rank #1 to #209)\n\n")
        f.write("| Rank | Trading Date | Trades | Stocks Traded | Total Capital Deployed (₹) | Gross P&L (₹) | Deductions (₹) | Net P&L (₹) | Result |\n")
        f.write("| :---: | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |\n")
        
        for idx, row in daily_stats.iterrows():
            d = row['trading_date']
            d_trades = trades[trades['trading_date'] == d]
            syms_str = ', '.join([f"`{s}`" for s in d_trades['symbol'].tolist()])
            pnl_sign = '+' if row['net_pnl'] >= 0 else ''
            g_sign = '+' if row['gross_pnl'] >= 0 else ''
            f.write(f"| {row['activity_rank']} | {d} | **{row['trade_count']}** | {syms_str} | ₹{row['total_capital']:,.0f} | {g_sign}₹{row['gross_pnl']:,.0f} | ₹{row['total_charges']:,.0f} | **{pnl_sign}₹{row['net_pnl']:,.0f}** | {row['wins']}W / {row['losses']}L |\n")
            
    print(f"Successfully saved complete markdown ranking to: {md_path}")

if __name__ == '__main__':
    generate_markdown_ranking()
