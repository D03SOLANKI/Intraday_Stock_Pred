# 🚀 Institutional Mid-Cap Momentum Engine (Tier 4 Dynamic Compounding)

[![Autonomous Intraday Trading Trigger](https://github.com/D03SOLANKI/Intraday_Stock_Pred/actions/workflows/intraday_trading_trigger.yml/badge.svg)](https://github.com/D03SOLANKI/Intraday_Stock_Pred/actions/workflows/intraday_trading_trigger.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

An institutional-grade, point-in-time momentum breakout trading system operating on the **NIFTY Midcap 150** universe. Features **zero look-ahead bias**, **dynamic +1.0% breakeven ratcheting**, **5% Average Daily Volume (ADV) liquidity protection**, and **Tier 4 dynamic capital compounding**.

---

## 📊 Key Audited Performance Metrics (5-Year History: 2021–2026)

*All results reflect full Indian statutory taxes (STT, Stamp Duty, GST, Exchange, SEBI, DP charges) and **0.40% round-trip execution slippage**.*

| Metric | Conservative Fixed Baseline | **Tier 4 Dynamic Compounding** | Institutional Benchmark |
| :--- | :---: | :---: | :--- |
| **Initial Capital** | ₹10,000,000.00 (₹1.00 Cr) | **₹10,000,000.00 (₹1.00 Cr)** | Starting capital |
| **Position Sizing** | Fixed ₹20 Lakhs / trade | **28% Equity Sizing (5% ADV Cap)** | Max 4 concurrent slots |
| **Total Trades Executed** | 1,099 trades | **1,099 trades** | 483 active days (~2.3 trades/day) |
| **Net Win Rate** | **75.71%** (832 wins) | **75.55%** (830 wins) | **p = 1.83e-39 (Welch t-test)** |
| **Net Profit Factor (PF)** | **25.75** | **19.78** | Gross Gains / Gross Losses |
| **Realized Net Profit (₹)**| **+₹30,286,458.35 (+302.9%)** | **+₹425,777,413.00 (+4,258%)** | Realized net gains |
| **Ending Portfolio Equity**| **₹40,286,458.35 (4.03×)** | **₹435,777,413.00 (43.58×)** | Final capital after 5 years |
| **Maximum Drawdown** | **-0.32%** | **-0.62%** | Strictly bounded under 1.0% |
| **Untouched Holdout (2025–26)**| **76.82% Win Rate** | **82.21% Win Rate** | 251 quarantined sessions |

---

## 🏛️ System Architecture

```
[09:14 AM IST] Pre-Market Screening ──► 20-DMA Proximity <= 2.5%, RSI (14) 45-60, t-1 ADV
                                                   │
[09:30 AM IST] Point-in-Time 15m Scan ──► Gap: +0.40% to +1.60%
                                           Gap-Fill Rejection: Low >= Prev_Close * 0.998
                                           Volume Surge: Vol_15m >= 1.60x
                                                   │
[09:30:15 IST] Order Execution       ──► Limit Buy (0.20% adverse entry slippage)
                                           Hard Stop Loss: -1.80%
                                           Breakeven Ratchet Trigger: +1.00%
                                           Target: +4.00%
                                                   │
[09:30 - 15:15] Intraday Manager     ──► At +1.0% gain: Stop moves to Entry * 1.002 (+0.20% locked)
                                           At 15:15 IST: Mandatory Intraday Auto-Square-Off
```

---

## ☁️ 24/7 Cloud Automation & Dashboard

### 1. Automated GitHub Actions Trigger
* **Schedule**: Automatically runs at **04:00 UTC (09:30 AM IST)** Monday through Friday.
* **Execution**: Evaluates opening 15-minute point-in-time metrics, checks 5% ADV caps, and generates `daily_live_scan_orders.csv`.
* **Auto-Commit**: Pushes updated orders directly to this repository, updating the Streamlit Cloud dashboard instantly.
* **Manual Dispatch**: You can also trigger a scan anytime from the **Actions** tab by clicking **Run workflow**.

### 2. Streamlit Cloud 24/7 Mobile Dashboard
* Deploy `app.py` directly to [Streamlit Community Cloud](https://share.streamlit.io).
* View live candlestick price brackets, stop loss levels, and daily top-gainer picks from your smartphone browser anywhere.

---

## 💻 Local Machine Usage

```powershell
# 1. Run live scanner manually
python live_scanner.py --equity 10000000.0

# 2. View generated actionable orders
cat daily_live_scan_orders.csv

# 3. Launch the local Streamlit dashboard
streamlit run app.py

# 4. Manage local background auto-boot daemon
powershell .\manage_daemon.ps1 status
```

---

## 📜 Complete Institutional Audit Reports
* **Forensic Audit Report**: [`Independent_Comprehensive_Forensic_Audit_Report.docx`](Independent_Comprehensive_Forensic_Audit_Report.docx) | [`.md`](Independent_Comprehensive_Forensic_Audit_Report.md)
* **Walk-Forward Overfitting Audit**: [`Walk_Forward_Overfitting_and_Validation_Audit.docx`](Walk_Forward_Overfitting_and_Validation_Audit.docx) | [`.md`](Walk_Forward_Overfitting_and_Validation_Audit.md)
* **Return Restoration Audit**: [`High_Alpha_Return_Restoration_and_Compounding_Audit.docx`](High_Alpha_Return_Restoration_and_Compounding_Audit.docx) | [`.md`](High_Alpha_Return_Restoration_and_Compounding_Audit.md)
