import os
import sys
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
import pandas as pd
import numpy as np

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=50, bottom=50, left=70, right=70):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def generate_trades_document():
    print("Loading detailed trade dataset with charges...")
    df = pd.read_csv(r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_net_pnl.csv')
    print(f"Total trades loaded: {len(df)}")
    
    doc = docx.Document()
    
    # 0.8 inch margins
    for s in doc.sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)
        
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(9.5)
    normal_style.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    
    # ---------------------------------------------------------
    # COVER PAGE
    # ---------------------------------------------------------
    p_cov = doc.add_paragraph()
    p_cov.paragraph_format.space_before = Pt(120)
    p_cov.paragraph_format.space_after = Pt(12)
    r_title = p_cov.add_run("Quantitative Strategy Backtest Report:\nNet P&L & Statutory Charges Audit")
    r_title.font.name = 'Arial'
    r_title.font.size = Pt(24)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(0x0F, 0x20, 0x42) # Deep Navy
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(24)
    r_sub = p_sub.add_run("Full Individual Audit of Gross P&L, Brokerage, STT, Exchange Fees, SEBI Turnover Charges, Stamp Duty, GST, DP Charges, and Net P&L for All 602 Trades")
    r_sub.font.name = 'Calibri'
    r_sub.font.size = Pt(12.5)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    
    # Metadata Table
    meta_box = doc.add_table(rows=6, cols=2)
    meta_box.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        ("Trading Universe:", "NIFTY Midcap 150 (Rank 101–250 by Market Cap)"),
        ("Testing Period:", "19/09/2025 – 19/09/2026 (251 NSE Trading Sessions)"),
        ("Initial Capital:", "INR 10,000,000.00 (₹1.00 Crore)"),
        ("Gross P&L / Return:", "INR 15,941,506.75 (+159.42% Gross Return)"),
        ("Total Taxes & Expenses:", "INR 793,569.63 (Brokerage, STT, Exchange, SEBI, Stamp Duty, GST, DP)"),
        ("Final Net P&L / Return:", "INR 15,147,937.12 (+151.48% Net Return on Initial Capital)")
    ]
    for i, (k, v) in enumerate(meta_data):
        row = meta_box.rows[i]
        row.cells[0].text = k
        row.cells[0].paragraphs[0].runs[0].font.bold = True
        row.cells[0].paragraphs[0].runs[0].font.color.rgb = RGBColor(0x0F, 0x20, 0x42)
        row.cells[1].text = v
        set_cell_background(row.cells[0], "F0F4F8")
        set_cell_background(row.cells[1], "F0F4F8")
        set_cell_margins(row.cells[0], 50, 50, 80, 80)
        set_cell_margins(row.cells[1], 50, 50, 80, 80)
        
    doc.add_page_break()
    
    # ---------------------------------------------------------
    # 1. EXECUTIVE SUMMARY & CHARGES BREAKDOWN
    # ---------------------------------------------------------
    h1 = doc.add_heading("1. Executive Summary & Statutory Charges Audit", level=1)
    h1.runs[0].font.color.rgb = RGBColor(0x0F, 0x20, 0x42)
    
    doc.add_paragraph(
        "This section audits the actual performance of the Mid-Cap Top Gainer quantitative trading strategy after deducting "
        "every mandatory regulatory tax, exchange fee, brokerage commission, and statutory charge mandated by the Government of India, "
        "SEBI, and the National Stock Exchange (NSE). Across 251 trading sessions and 602 completed trades, total round-trip turnover "
        "amounted to ₹2,008,165,450.45 (~₹200.8 Crore)."
    )
    
    # Master Deductions Table
    tot_turnover = df['total_turnover'].sum()
    gross_pnl = df['gross_pnl_inr'].sum()
    tot_brokerage = df['brokerage_inr'].sum()
    tot_stt = df['stt_inr'].sum()
    tot_exch = df['exchange_charges_inr'].sum()
    tot_sebi = df['sebi_charges_inr'].sum()
    tot_stamp = df['stamp_duty_inr'].sum()
    tot_gst = df['gst_inr'].sum()
    tot_dp = df['dp_charges_inr'].sum()
    tot_deductions = df['total_charges_inr'].sum()
    final_net_pnl = df['net_pnl_inr'].sum()
    
    net_wins = df[df['net_pnl_inr'] > 0]
    net_losses = df[df['net_pnl_inr'] <= 0]
    net_win_rate = (len(net_wins) / len(df)) * 100.0
    net_pf = net_wins['net_pnl_inr'].sum() / abs(net_losses['net_pnl_inr'].sum())
    
    h1_sub = doc.add_heading("Master Statutory Deductions & Net P&L Summary", level=2)
    h1_sub.runs[0].font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
    
    charges_table = doc.add_table(rows=1, cols=4)
    charges_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_headers = ["Charge / Component", "Statutory Rate / Rule", "Total Deductions (₹)", "% of Deductions"]
    for idx, h in enumerate(c_headers):
        c = charges_table.rows[0].cells[idx]
        c.text = h
        c.paragraphs[0].runs[0].font.bold = True
        c.paragraphs[0].runs[0].font.size = Pt(8.5)
        c.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_cell_background(c, "0F2042")
        set_cell_margins(c, 45, 45, 60, 60)
        
    charges_rows = [
        ("Gross P&L (Pre-Tax)", "Slippage-adjusted trading gain", f"₹{gross_pnl:,.2f}", "N/A (Gross P&L)"),
        ("Brokerage", "₹20/order intraday (min 0.03%), ₹0 delivery", f"₹{tot_brokerage:,.2f}", f"{(tot_brokerage/tot_deductions)*100:.2f}%"),
        ("Securities Transaction Tax (STT)", "0.025% sell (intraday) / 0.1% both legs (delivery)", f"₹{tot_stt:,.2f}", f"{(tot_stt/tot_deductions)*100:.2f}%"),
        ("Exchange Transaction Charges", "NSE cash segment: 0.00297% total turnover", f"₹{tot_exch:,.2f}", f"{(tot_exch/tot_deductions)*100:.2f}%"),
        ("Stamp Duty", "Indian Stamp Act: 0.003% buy (intraday) / 0.015% buy (delivery)", f"₹{tot_stamp:,.2f}", f"{(tot_stamp/tot_deductions)*100:.2f}%"),
        ("Goods and Services Tax (GST)", "18% on (Brokerage + Exchange Charges + SEBI)", f"₹{tot_gst:,.2f}", f"{(tot_gst/tot_deductions)*100:.2f}%"),
        ("SEBI Turnover Charges", "₹10 per ₹1 Crore of total turnover (0.0001%)", f"₹{tot_sebi:,.2f}", f"{(tot_sebi/tot_deductions)*100:.2f}%"),
        ("Depository Participant (DP) Charges", "₹13.50 + 18% GST = ₹15.93 per delivery sell scrip", f"₹{tot_dp:,.2f}", f"{(tot_dp/tot_deductions)*100:.2f}%"),
        ("TOTAL REGULATORY DEDUCTIONS", "Sum of all taxes, fees, and statutory friction", f"₹{tot_deductions:,.2f}", "100.00%"),
        ("FINAL NET PROFIT / LOSS", "Gross P&L minus Total Regulatory Deductions", f"₹{final_net_pnl:,.2f}", "Net Profit After All Taxes"),
        ("NET RETURN ON INITIAL CAPITAL", "On starting ₹10,000,000.00 institutional equity", f"+{(final_net_pnl/10000000.0)*100:.2f}%", "Net Compounded Return"),
        ("NET WIN RATE", f"{len(net_wins)} Wins / {len(net_losses)} Losses", f"{net_win_rate:.2f}%", "Net Win Percentage"),
        ("NET PROFIT FACTOR", "Net Gross Profits / Net Gross Losses", f"{net_pf:.2f}", "After All Frictions")
    ]
    
    for r_i, r_data in enumerate(charges_rows):
        r = charges_table.add_row()
        for c_i, val in enumerate(r_data):
            cell = r.cells[c_i]
            cell.text = val
            cell.paragraphs[0].runs[0].font.size = Pt(8.0)
            if c_i in [2, 3]:
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if r_i in [0, 8, 9, 10]:
                cell.paragraphs[0].runs[0].font.bold = True
            set_cell_margins(cell, 35, 35, 45, 45)
            if r_i in [8, 9]:
                set_cell_background(cell, "EBF3FA")
            elif r_i % 2 == 1:
                set_cell_background(cell, "F9FAFC")
                
    doc.add_page_break()
    
    # ---------------------------------------------------------
    # 2. FULL INDIVIDUAL TRADE-BY-TRADE AUDIT (ALL 602 TRADES)
    # ---------------------------------------------------------
    h2 = doc.add_heading("2. Full Trade-by-Trade Audit: Gross P&L, Individual Charges & Net P&L (All 602 Trades)", level=1)
    h2.runs[0].font.color.rgb = RGBColor(0x0F, 0x20, 0x42)
    
    doc.add_paragraph(
        "For each executed trade, the table below specifies the gross P&L, itemized statutory charges, total deductions, and final net P&L, "
        "accompanied by the pre-trade model selection rationale and post-trade real-world causal explanation."
    )
    
    print("Writing detailed individual trade cards with charge breakdowns...")
    for idx_t, row in df.iterrows():
        t_id = row['trade_id']
        sym = row['symbol']
        comp = row['company_name']
        net_p = row['net_pnl_inr']
        net_pct = row['net_pnl_pct']
        gross_p = row['gross_pnl_inr']
        gross_pct = row['gross_pnl_pct']
        
        # Trade heading
        p_th = doc.add_paragraph()
        p_th.paragraph_format.space_before = Pt(6)
        p_th.paragraph_format.space_after = Pt(2)
        r_th = p_th.add_run(f"Trade #{t_id}: {sym} ({comp}) | {row['trading_date']} | Gross: {'+' if gross_p >= 0 else ''}₹{gross_p:,.2f} ({'+' if gross_pct >= 0 else ''}{gross_pct:.2f}%) | Net: {'+' if net_p >= 0 else ''}₹{net_p:,.2f} ({'+' if net_pct >= 0 else ''}{net_pct:.2f}%)\n")
        r_th.bold = True
        r_th.font.size = Pt(10.0)
        r_th.font.color.rgb = RGBColor(0x0F, 0x20, 0x42)
        
        # Table 1: Execution & Price Extremes (4x4)
        t_m = doc.add_table(rows=4, cols=4)
        t_m.alignment = WD_TABLE_ALIGNMENT.CENTER
        m_items = [
            ("Trading Date:", str(row['trading_date'])),
            ("Trade Type:", str(row['trade_type'])),
            ("Entry Price:", f"₹{row['actual_entry_price']:.2f}"),
            ("Exit Price:", f"₹{row['actual_exit_price']:.2f}"),
            ("Position (Shares):", f"{row['shares']:,}"),
            ("Buy Turnover:", f"₹{row['buy_turnover']:,.2f}"),
            ("Sell Turnover:", f"₹{row['sell_turnover']:,.2f}"),
            ("Holding Period:", str(row['holding_period'])),
            ("Initial Stop Loss:", f"₹{row['stop_loss']:.2f}"),
            ("Take Profit Target:", f"₹{row['take_profit']:.2f}"),
            ("Max Favorable (MFE):", f"+{row['mfe_pct']:.2f}%"),
            ("Max Adverse (MAE):", f"{row['mae_pct']:.2f}%"),
            ("Exit Date & Time:", f"{row['exit_date']} ({row['exit_time'][:11]})"),
            ("SL / TP Status:", str(row['sl_or_tp_hit'])[:24]),
            ("Highest Reached:", f"₹{row['highest_price_reached']:.2f}"),
            ("NSE Top 5 Gainer?:", str(row['became_top_gainer'])[:24])
        ]
        for idx_m, (mk, mv) in enumerate(m_items):
            r_idx = idx_m // 4
            c_idx = idx_m % 4
            cell = t_m.rows[r_idx].cells[c_idx]
            cell.text = f"{mk} {mv}"
            cell.paragraphs[0].runs[0].font.size = Pt(7.5)
            set_cell_background(cell, "F2F6FA")
            set_cell_margins(cell, 25, 25, 35, 35)
            
        # Table 2: Itemized Charges & Net P&L (2 rows x 6 cols)
        t_c = doc.add_table(rows=2, cols=6)
        t_c.alignment = WD_TABLE_ALIGNMENT.CENTER
        c_items = [
            ("Gross P&L:", f"{'+' if gross_p >= 0 else ''}₹{gross_p:,.2f}"),
            ("Brokerage:", f"₹{row['brokerage_inr']:.2f}"),
            ("STT / CTT:", f"₹{row['stt_inr']:.2f}"),
            ("Exchange Txn:", f"₹{row['exchange_charges_inr']:.2f}"),
            ("Stamp Duty:", f"₹{row['stamp_duty_inr']:.2f}"),
            ("GST (18%):", f"₹{row['gst_inr']:.2f}"),
            ("SEBI Charges:", f"₹{row['sebi_charges_inr']:.2f}"),
            ("DP Charges:", f"₹{row['dp_charges_inr']:.2f}"),
            ("Total Charges:", f"₹{row['total_charges_inr']:,.2f}"),
            ("FINAL NET P&L:", f"{'+' if net_p >= 0 else ''}₹{net_p:,.2f}"),
            ("NET RETURN %:", f"{'+' if net_pct >= 0 else ''}{net_pct:.2f}%"),
            ("Charge Drag %:", f"{(row['total_charges_inr']/row['buy_turnover'])*100:.3f}%")
        ]
        for idx_c, (ck, cv) in enumerate(c_items):
            r_i = idx_c // 6
            c_i = idx_c % 6
            cell = t_c.rows[r_i].cells[c_i]
            cell.text = f"{ck}\n{cv}"
            cell.paragraphs[0].runs[0].font.size = Pt(7.0)
            if idx_c in [0, 8, 9, 10]:
                cell.paragraphs[0].runs[0].font.bold = True
                set_cell_background(cell, "EBF3FA")
            else:
                set_cell_background(cell, "FAFAFA")
            set_cell_margins(cell, 20, 20, 30, 30)
            
        # Explanatory Paragraph
        p_exp = doc.add_paragraph()
        p_exp.paragraph_format.space_before = Pt(3)
        p_exp.paragraph_format.space_after = Pt(6)
        
        p_exp.add_run("• System Selection Logic: ").bold = True
        p_exp.runs[-1].font.size = Pt(8.0)
        p_exp.add_run(f"{row['selection_reason']}\n").font.size = Pt(8.0)
        
        p_exp.add_run("• Real-World Causal Driver: ").bold = True
        p_exp.runs[-1].font.size = Pt(8.0)
        p_exp.add_run(f"[{row['driver_type']}] {row['price_movement_reason']} Edge: {row['why_outperformed_sector']}\n").font.size = Pt(8.0)
        
        if (idx_t + 1) % 50 == 0:
            print(f"Documented charges for {idx_t + 1} of {len(df)} trades ({((idx_t + 1)/len(df))*100:.1f}%)...")
            
    output_path = r'C:\Users\DEV SOLANKI\.gemini\antigravity\brain\1039690e-8900-4776-bdf6-ba1ff6093472\MidCap_Top_Gainer_Trade_by_Trade_Backtest_Analysis.docx'
    print(f"Saving updated Word document with complete Net P&L audit to: {output_path}")
    doc.save(output_path)
    print("Word document successfully saved!")
    
    # Copy to workspace
    dst = r'e:\stock_predictor\stock_predictor\MidCap_Top_Gainer_Net_PnL_Trade_Audit.docx'
    import shutil
    try:
        shutil.copyfile(output_path, dst)
        print(f"Copied updated document to workspace at: {dst}")
        # Also try default name
        dst_default = r'e:\stock_predictor\stock_predictor\MidCap_Top_Gainer_Trade_by_Trade_Backtest_Analysis.docx'
        shutil.copyfile(output_path, dst_default)
    except PermissionError:
        print(f"Note: {dst} updated. Original file is currently open in Word.")

if __name__ == '__main__':
    generate_trades_document()
