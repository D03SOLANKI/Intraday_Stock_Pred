import os
import sys
import pandas as pd
import numpy as np
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=40, bottom=40, left=60, right=60):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def generate_prediction_tables():
    # 1-Year Dataset
    df1 = pd.read_csv(r'e:\stock_predictor\stock_predictor\top_gainer_predictions_accuracy.csv')
    rank1_df = pd.read_csv(r'e:\stock_predictor\stock_predictor\rank1_top_gainer_predictions.csv')
    
    # 5-Year Dataset
    df5 = pd.read_csv(r'e:\stock_predictor\stock_predictor\strategy_backtest_trades_5year_net_pnl.csv')
    rank1_5yr = df5[df5['pred_rank_num'] == 1].copy()
    
    print(f"Loaded 1-Year: {len(df1)} predictions ({len(rank1_df)} Rank #1)")
    print(f"Loaded 5-Year: {len(df5)} predictions ({len(rank1_5yr)} Rank #1)")
    
    # Generate complete Markdown file for all 208 Rank #1 predictions
    md_path = r'C:\Users\DEV SOLANKI\.gemini\antigravity\brain\1039690e-8900-4776-bdf6-ba1ff6093472\all_top_gainer_predictions_accuracy.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# Complete Top-Gainer Prediction Accuracy Audit\n\n")
        f.write("## 1. Summary Statistics (1-Year vs 5-Year)\n\n")
        f.write("| Evaluation Tier | 1-Year Study (2025–2026) | 5-Year Study (2021–2026) | Random Baseline |\n")
        f.write("| :--- | :---: | :---: | :---: |\n")
        f.write(f"| **Total Rank #1 Predictions** | **{len(rank1_df)}** | **{len(rank1_5yr)}** | 150 mid-caps |\n")
        f.write(f"| **Exact Rank #1 Hits** | **{(rank1_df['actual_universe_rank'] == 1).sum()} ({(rank1_df['actual_universe_rank'] == 1).mean()*100:.2f}%)** | **{(rank1_5yr['actual_universe_rank'] == 1).sum()} ({(rank1_5yr['actual_universe_rank'] == 1).mean()*100:.2f}%)** | 0.67% (1/150) |\n")
        f.write(f"| **Top-5 Hits** | **{(rank1_df['actual_universe_rank'] <= 5).sum()} ({(rank1_df['actual_universe_rank'] <= 5).mean()*100:.2f}%)** | **{(rank1_5yr['actual_universe_rank'] <= 5).sum()} ({(rank1_5yr['actual_universe_rank'] <= 5).mean()*100:.2f}%)** | 3.33% (5/150) |\n")
        f.write(f"| **Top-10 Hits** | **{(rank1_df['actual_universe_rank'] <= 10).sum()} ({(rank1_df['actual_universe_rank'] <= 10).mean()*100:.2f}%)** | **{(rank1_5yr['actual_universe_rank'] <= 10).sum()} ({(rank1_5yr['actual_universe_rank'] <= 10).mean()*100:.2f}%)** | 6.67% (10/150) |\n")
        f.write(f"| **Top Decile (Top 20)** | **{(rank1_df['actual_universe_rank'] <= 20).sum()} ({(rank1_df['actual_universe_rank'] <= 20).mean()*100:.2f}%)** | **{(rank1_5yr['actual_universe_rank'] <= 20).sum()} ({(rank1_5yr['actual_universe_rank'] <= 20).mean()*100:.2f}%)** | 13.33% (20/150) |\n")
        f.write(f"| **Incorrect (Outside Top 5)** | **{(rank1_df['actual_universe_rank'] > 5).sum()} ({(rank1_df['actual_universe_rank'] > 5).mean()*100:.2f}%)** | **{(rank1_5yr['actual_universe_rank'] > 5).sum()} ({(rank1_5yr['actual_universe_rank'] > 5).mean()*100:.2f}%)** | 96.67% |\n")
        f.write(f"| **Median Actual Rank** | **Rank #{rank1_df['actual_universe_rank'].median():.0f}** | **Rank #{rank1_5yr['actual_universe_rank'].median():.0f}** | Rank #75 |\n\n")
        
        f.write("## 2. Complete Ledger of All 208 Rank #1 Predictions (1-Year Study)\n\n")
        f.write("| # | Predicted Date | Stock Name | Symbol | Predicted Rank | Actual Rank | Daily Return (%) | Outcome |\n")
        f.write("| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- |\n")
        
        for idx, row in rank1_df.iterrows():
            f.write(f"| {idx+1} | {row['trading_date']} | {row['company_name']} | `{row['symbol']}` | {row['predicted_rank']} | **Rank #{row['actual_universe_rank']}** | {row['daily_return']:+.2f}% | {row['prediction_outcome']} |\n")
            
    print(f"Saved complete markdown report to: {md_path}")
    
    # Also create Word Document
    doc = docx.Document()
    for s in doc.sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)
        
    p_t = doc.add_paragraph()
    p_t.paragraph_format.space_before = Pt(40)
    p_t.paragraph_format.space_after = Pt(8)
    r = p_t.add_run("Top-Gainer Prediction Accuracy Audit:\nComplete Prediction Ledger")
    r.font.name = 'Arial'
    r.font.size = Pt(20)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0x0F, 0x20, 0x42)
    
    p_sub = doc.add_paragraph("Comprehensive Verification of All Daily Top-Gainer Predictions Against Actual NSE Outcomes")
    p_sub.runs[0].font.italic = True
    
    doc.add_heading("1. All 208 Rank #1 Top-Gainer Predictions", level=2)
    t = doc.add_table(rows=1, cols=7)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["#", "Date", "Stock Name", "Symbol", "Pred Rank", "Actual Rank", "Outcome"]
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(8.0)
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_cell_background(cell, "0F2042")
        set_cell_margins(cell, 30, 30, 40, 40)
        
    for idx, row in rank1_df.iterrows():
        r = t.add_row()
        vals = [
            str(idx + 1),
            str(row['trading_date']),
            str(row['company_name'])[:24],
            str(row['symbol']),
            str(row['predicted_rank']),
            f"Rank #{row['actual_universe_rank']}",
            str(row['prediction_outcome'])
        ]
        for c_i, val in enumerate(vals):
            c = r.cells[c_i]
            c.text = val
            c.paragraphs[0].runs[0].font.size = Pt(7.0)
            if c_i in [0, 4, 5]:
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            set_cell_margins(c, 20, 20, 30, 30)
            if idx % 2 == 1:
                set_cell_background(c, "F9FAFC")
            if row['actual_universe_rank'] == 1:
                set_cell_background(c, "EBF5FB")
                
    doc_path = r'C:\Users\DEV SOLANKI\.gemini\antigravity\brain\1039690e-8900-4776-bdf6-ba1ff6093472\Top_Gainer_Predictions_Accuracy_Report.docx'
    doc.save(doc_path)
    print(f"Saved Word report to: {doc_path}")
    
    # Copy to workspace
    dst = r'e:\stock_predictor\stock_predictor\Top_Gainer_Predictions_Accuracy_Report.docx'
    import shutil
    try:
        shutil.copyfile(doc_path, dst)
        print(f"Copied to workspace: {dst}")
    except Exception as e:
        print(f"Copy note: {e}")

if __name__ == '__main__':
    generate_prediction_tables()
