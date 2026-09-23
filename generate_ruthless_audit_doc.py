"""
Generate the Word Document: 'System_Ruthless_Forensic_Audit_Report.docx'
"""

import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_callout(doc, text_paragraphs, title="CRITICAL AUDIT FINDING", bg_color="FEF2F2", border_color="991B1B"):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Inches(6.5)
    
    cell = table.cell(0, 0)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'''
        <w:tcBorders {nsdecls("w")}>
            <w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/>
            <w:top w:val="none"/>
            <w:right w:val="none"/>
            <w:bottom w:val="none"/>
        </w:tcBorders>
    ''')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    run_title = p.add_run(f"🚨 {title}\n")
    run_title.font.bold = True
    run_title.font.size = Pt(10.5)
    run_title.font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    for tp in text_paragraphs:
        p2 = cell.add_paragraph()
        p2.paragraph_format.space_before = Pt(2)
        p2.paragraph_format.space_after = Pt(2)
        r = p2.add_run(tp)
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0x45, 0x0A, 0x0A)

def format_table_header(row, col_widths, headers, bg_color="991B1B", text_color="FFFFFF"):
    for idx, name in enumerate(headers):
        cell = row.cells[idx]
        cell.width = col_widths[idx]
        set_cell_background(cell, bg_color)
        set_cell_margins(cell, top=120, bottom=120, left=120, right=120)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(name)
        r.font.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor.from_string(text_color)

def add_table_data_row(row, col_widths, data, is_even=False, alignments=None):
    bg_color = "F8FAFC" if is_even else "FFFFFF"
    for idx, val in enumerate(data):
        cell = row.cells[idx]
        cell.width = col_widths[idx]
        set_cell_background(cell, bg_color)
        set_cell_margins(cell, top=90, bottom=90, left=110, right=110)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        if alignments and idx < len(alignments):
            p.alignment = alignments[idx]
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(str(val))
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)

def build_audit_doc(output_path: str):
    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
        
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(10)
    normal_style.font.color.rgb = RGBColor(0x2D, 0x37, 0x48)
    
    # Title
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(2)
    r_title = p_title.add_run("RUTHLESS SYSTEM AUDIT & FAILURE POST-MORTEM")
    r_title.font.size = Pt(22)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(16)
    r_sub = p_sub.add_run("Unvarnished Forensic Audit: Root Cause Analysis of 4-Stock Slicing, Large-Cap Universe Contamination, Failure to Lock ₹1,04,000 Profit, Complete Hardcoding Census, and Verification Test Suite")
    r_sub.font.size = Pt(11)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(0x4A, 0x55, 0x68)
    
    add_callout(doc, [
        "AUDIT STANCE: Zero defensive rationalization. Zero assumptions of correctness. Every component has been evaluated against cold code and empirical execution logs.",
        "PRIMARY VERDICT: Multiple critical systemic failures confirmed: (1) Arbitrary candidate clipping via .head(4) in place of strategy selectivity enforcement; (2) Hardcoded 27-ticker list containing Large-Caps (JINDALSTEL, INDUSTOWER, BHEL) directly violating the Mid-Cap-only mandate; (3) Complete absence of portfolio-level profit-taking logic, coupled with a dormant intraday daemon loop that failed to poll ticks and hardcoded entry prices at square-off; (4) Zero machine learning/AI—the system is 100% heuristic rule-based."
    ], title="BLUNT AUDIT VERDICT: SYSTEM BROKEN IN LIVE PRODUCTION", bg_color="FEF2F2", border_color="991B1B")
    
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    # 1. Confirmed Bugs
    h1 = doc.add_heading("1. Confirmed System Bugs", level=1)
    h1.runs[0].font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    bugs_table = doc.add_table(rows=6, cols=4)
    bugs_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    b_widths = [Inches(1.0), Inches(1.8), Inches(1.8), Inches(1.9)]
    format_table_header(bugs_table.rows[0], b_widths, ["Bug ID", "Subsystem Affected", "Defect Description", "Operational Impact"])
    
    bug_data = [
        ("BUG-01", "live_scanner.py\n(Line 151)", "Arbitrary Truncation via .head(4) instead of Selectivity Check", "When 11 stocks qualified, code arbitrarily sliced top 4 instead of rejecting day due to diffuse momentum."),
        ("BUG-02", "live_scanner.py\n(Lines 18-33)", "Hardcoded Universe Contaminated with Large-Caps", "Bypassed nifty_midcap_150.csv using hardcoded list containing JINDALSTEL & INDUSTOWER (Nifty 100)."),
        ("BUG-03", "order_manager.py\n(Missing Feature)", "Zero Portfolio-Level Take-Profit Logic", "System reached +Rs. 1,04,000 profit but had no rule to square off at portfolio milestone; ended in a loss."),
        ("BUG-04", "daemon.py\n(Lines 153-162)", "Dormant Intraday Loop (No Live Tick Polling)", "Daemon simply did time.sleep(30); never called order_mgr.process_tick() during market hours."),
        ("BUG-05", "daemon.py\n(Line 169)", "Hardcoded Entry Price Exit at 15:15 IST", "Daemon passed market_px = entry_price to square-off, falsifying exit prices and ignoring actual market.")
    ]
    for idx, row_data in enumerate(bug_data, 1):
        add_table_data_row(bugs_table.rows[idx], b_widths, row_data, is_even=(idx % 2 == 0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(12)
    
    # 2. Hardcoded Logic Census
    h2 = doc.add_heading("2. Comprehensive Hardcoded Logic Census", level=1)
    h2.runs[0].font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    hc_table = doc.add_table(rows=9, cols=5)
    hc_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hc_widths = [Inches(1.5), Inches(1.3), Inches(0.6), Inches(1.3), Inches(1.8)]
    format_table_header(hc_table.rows[0], hc_widths, ["File", "Function", "Line", "Hardcoded Value", "Audit Finding & Action"])
    
    hc_data = [
        ("live_scanner.py", "Global", "18-22", "CATALYST_SYMBOLS (27)", "Hardcoded ticker list containing Large-Caps. REMOVED."),
        ("dynamic_compounding.py", "__init__", "21", "max_concurrent_positions = 4", "Hardcoded 4 slots without selectivity rule. Changed to 2."),
        ("dynamic_compounding.py", "__init__", "44-48", "self.catalyst_symbols", "Arbitrary ticker set adding artificial +0.20 score bias. REMOVED."),
        ("live_scanner.py", "run_scanner", "151", "eligible.head(4)", "Arbitrary truncation ignoring day selectivity. Replaced with rejection."),
        ("autonomous_daemon.py", "run_daemon", "169", "market_px = entry_price", "Faked exit price at entry minus slippage. Replaced with real tick fetch."),
        ("point_in_time_strategy.py", "__init__", "16", "max_positions = 5", "Hardcoded 5 slots from legacy model. Obsolete."),
        ("improved_point_in_time.py", "__init__", "22", "max_positions = 8", "Hardcoded 8 slots from Candidate B. Obsolete."),
        ("order_manager.py", "__init__", "20", "take_profit_pct = 0.040", "Only per-stock exit; zero portfolio profit ceiling. Added Rs. 1L target.")
    ]
    for idx, row_data in enumerate(hc_data, 1):
        add_table_data_row(hc_table.rows[idx], hc_widths, row_data, is_even=(idx % 2 == 0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(12)
    
    # 3. Root Cause: 4-Stock Prediction
    h3 = doc.add_heading("3. Exact Root Cause: 4-Stock Prediction", level=1)
    h3.runs[0].font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    p = doc.add_paragraph()
    p.add_run(
        "• Exact Code Responsible: live_scanner.py Line 151: top_candidates = eligible.head(strat.max_concurrent_positions).copy() "
        "and dynamic_compounding_strategy.py Line 21: self.max_concurrent_positions = 4.\n\n"
        "• Hardcoded vs. Dynamic: The number of predictions was HARDCODED to 4 via .head(4). It was NOT dynamically determined.\n\n"
        "• The Real Violation: In today's live market session (2026-09-23), 11 mid-cap candidates qualified. When 11 stocks pass opening filters simultaneously, "
        "it indicates broad market beta expansion rather than an isolated, idiosyncratic top gainer. "
        "Instead of detecting this selectivity failure and rejecting the day, the system blindly sliced the top 4 using .head(4).\n\n"
        "• The Implemented Strict Rule: If qualifying opportunities > 2, the day is STRICTLY REJECTED. Zero orders placed. 100% Cash preserved."
    )
    
    # 4. Root Cause: Large-Cap Prediction
    h4 = doc.add_heading("4. Exact Root Cause: Large-Cap Predictions (JINDALSTEL & INDUSTOWER)", level=1)
    h4.runs[0].font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    p = doc.add_paragraph()
    p.add_run(
        "• Exact Code Responsible: live_scanner.py Lines 18-22 and Lines 30-33: if symbols is None: symbols = CATALYST_SYMBOLS.\n\n"
        "• Mechanism of Contamination: live_scanner.py NEVER loaded the official nifty_midcap_150.csv universe. "
        "Instead, it defaulted to a hardcoded list of 27 tickers (CATALYST_SYMBOLS) that explicitly contained JINDALSTEL (Market Cap Rs. 1,15,000+ Cr) "
        "and INDUSTOWER (Market Cap Rs. 1,00,000+ Cr). Both are NIFTY 100 / LARGE-CAP STOCKS. In fact, JINDALSTEL is not even present in nifty_midcap_150.csv!\n\n"
        "• The Implemented Strict Rule: All scans now dynamically load from nifty_midcap_150.csv and cross-check against LARGE_CAP_EXCLUSIONS (Top 100). "
        "Any Large-Cap stock is immediately purged. Attempted entry raises a hard system error."
    )
    
    # 5. Root Cause: Failure to Exit at Rs. 1,04,000 Profit
    h5 = doc.add_heading("5. Exact Root Cause: Failure to Exit at ₹1,04,000 Profit", level=1)
    h5.runs[0].font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    p = doc.add_paragraph()
    p.add_run(
        "• Was there an actual rule capable of triggering the exit? NO. The system had ZERO portfolio-level take-profit logic.\n\n"
        "• The Compounding Flaw: In autonomous_trading_daemon.py Lines 153-162, the intraday monitoring loop was completely dormant: "
        "it executed time.sleep(30) without downloading live price ticks and without calling order_mgr.process_tick()! "
        "Even if individual positions reached +4.0%, the daemon was blind to it.\n\n"
        "• The Square-Off Sham: At 15:15 IST, Line 169 hardcoded market_px = {p['symbol']: p['entry_price']}. "
        "It exited every trade at entry price minus slippage, generating a synthetic -0.24% loss while ignoring real market prices.\n\n"
        "• The Implemented Strict Rule: Implemented order_mgr.process_portfolio_ticks() with a mandatory Portfolio Profit Target of Rs. 1,00,000. "
        "The daemon polls 1-minute ticks live; the moment portfolio unrealized P&L touches Rs. 1,00,000, ALL positions are instantly squared off to lock profit."
    )
    
    # 6. Look-Ahead Bias & Learning Reality
    h6 = doc.add_heading("6. Look-Ahead Bias & Learning Reality Audit", level=1)
    h6.runs[0].font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)
    
    p = doc.add_paragraph()
    p.add_run(
        "• Look-Ahead Bias Finding: Historical backtests in run_strategy_backtest.py used rng_pos = (Close - Low) / (High - Low) from daily bars, "
        "leaking the 15:30 IST close into the 09:30 AM signal (+0.718 correlation with intraday return). "
        "This artificially inflated historical win rates to 84.7%. When tested point-in-time, the naive baseline collapsed to 24.3% win rate.\n\n"
        "• Learning Reality Verdict: The system is 100% HEURISTIC RULE-BASED. It is NOT learning, NOT adaptive, and NOT AI-driven. "
        "There is no machine learning model, no neural network, and no Bayesian updating. "
        "The 'CRMV score' is a static linear equation with hand-chosen weights (0.50, 0.35, 0.15)."
    )
    
    # 7. Test Results
    h7 = doc.add_heading("7. Verification Test Suite Results (13/13 Passed)", level=1)
    h7.runs[0].font.color.rgb = RGBColor(0x16, 0x65, 0x34)
    
    t_table = doc.add_table(rows=14, cols=3)
    t_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    t_widths = [Inches(1.0), Inches(3.2), Inches(2.3)]
    format_table_header(t_table.rows[0], t_widths, ["Test #", "Test Description", "Result"], bg_color="166534")
    
    test_rows = [
        ("Test 01", "0 valid stocks -> 0 trades (100% Cash preserved)", "PASSED (0 trades)"),
        ("Test 02", "1 valid stock -> Exactly 1 trade generated", "PASSED (1 trade)"),
        ("Test 03", "2 valid stocks -> Exactly 2 trades generated", "PASSED (2 trades)"),
        ("Test 04", "3 valid stocks -> REJECTED (0 trades, selectivity enforced)", "PASSED (Day Rejected)"),
        ("Test 05", "4+ valid stocks -> REJECTED (0 trades, selectivity enforced)", "PASSED (Day Rejected)"),
        ("Test 06", "Large-Caps (JINDALSTEL, BHEL, etc.) mixed with Mid-Caps", "PASSED (Large-Caps Purged)"),
        ("Test 07", "No valid Mid-Cap candidates -> 0 trades", "PASSED (0 trades)"),
        ("Test 08", "Portfolio profit target reached (>= Rs. 1,00,000)", "PASSED (Instant Square-Off & Lock)"),
        ("Test 09", "Portfolio profit target not reached (< Rs. 1,00,000)", "PASSED (Active Trailing Maintained)"),
        ("Test 10", "Multiple positions aggregated P&L tracking", "PASSED (Accurate Sum)"),
        ("Test 11", "Exit signal generation on Stop Loss trigger", "PASSED (Position Closed at SL)"),
        ("Test 12", "Exit execution failure fallback handling", "PASSED (Graceful Fallback)"),
        ("Test 13", "Missing or stale broker order CSV handling", "PASSED (Zero Crash)")
    ]
    for idx, row_data in enumerate(test_rows, 1):
        add_table_data_row(t_table.rows[idx], t_widths, row_data, is_even=(idx % 2 == 0))
        
    doc.save(output_path)
    print(f"Audit document generated at: {output_path}")

if __name__ == "__main__":
    local_path = r"e:\stock_predictor\stock_predictor\System_Ruthless_Forensic_Audit_Report.docx"
    build_audit_doc(local_path)
    brain_path = r"C:\Users\DEV SOLANKI\.gemini\antigravity\brain\1039690e-8900-4776-bdf6-ba1ff6093472\System_Ruthless_Forensic_Audit_Report.docx"
    build_audit_doc(brain_path)
