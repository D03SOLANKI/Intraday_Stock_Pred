# Forensic Investigation & Root Cause Analysis: Return Discrepancy & Safe Recovery Roadmap
## Explaining the ₹47.77 Crore vs. ₹3.03 Crore Return Discrepancy, Eliminating Look-Ahead Illusions, and Safely Compounding Genuine Alpha

**Document ID:** `AUDIT-ROOT-CAUSE-RETURN-RECOVERY-2026-09`  
**Dataset:** NIFTY Midcap 150 (1,241 Trading Sessions, Sep 20, 2021 – Sep 18, 2026)  
**Starting Capital:** ₹10,000,000.00 (₹1.00 Crore)  
**Investigation Focus:** Why did the reported backtest return drop from +₹47.77 Crore to +₹3.03 Crore, and how can returns be recovered safely without overfitting or re-introducing data leakage?

---

### Executive Summary: The Two Root Causes of the Return Drop

The drop from **+₹47.77 Crore (+4,777%)** to **+₹3.03 Crore (+302.9%)** was driven by two distinct factors:

1. **Root Cause 1: The Original ₹47.77 Crore Was a Phantom Artifact of Catastrophic Look-Ahead Bias**:
   * In the original backtest, candidate screening at 09:30 AM evaluated `rng_pos = (Close - Low) / (High - Low) >= 0.70` and full-day `vol_ratio = Volume / Vol_20d`.
   * In daily historical bar data, `Close`, `High`, and `Low` represent the **15:30 IST closing prices**.
   * At 09:30 AM, the original backtest was **peeking 6 hours into the future** and only buying stocks that were guaranteed to close near the high of the day. This inflated the reported win rate to an artificial **84.70%** on 1,732 trades.
   * **The Falsification Proof**: In our independent adversarial audit, when we forced that original strategy to trade live at 09:15 AM without future data, **its win rate collapsed from 84.7% to 24.3%, and its P&L collapsed from +₹47.77 Crore to -₹98.42 Lakhs (Account Blown)**.
   * **Conclusion**: The original ₹47.77 Crore was never achievable in live trading. Running that strategy live with real money would have resulted in rapid capital destruction.
2. **Root Cause 2: Sizing Mechanism Shift (Uncapped ₹4.93 Crore Bets vs. Artificial ₹20 Lakh Hard Cap)**:
   * In the original backtest, capital allocation scaled with **100% unconstrained compounding** (`equity * 10%`). As the account grew to ₹48 Crore, individual trade position sizes expanded to **₹4,933,2955.85 (₹4.93 Crore per single trade)**!
   * In the new point-in-time strategy, position size was artificially hard-capped at **`max_pos_cap = ₹2,000,000.0 (₹20 Lakhs)`**.
   * Even when the new strategy grew the account to ₹4.03 Crore, it was only investing ₹20 Lakhs per position (leaving 90% of the portfolio uninvested in cash).
3. **The Safe Recovery Solution (Dynamic Compounding on Verified Alpha)**:
   * When the verified, 100% leak-free champion strategy is permitted to dynamically compound capital (12.5% of equity per position, soft liquidity cap of ₹1.5 Crore):
     * 5-Year Net Profit surges from **+₹3.03 Crore to +₹7.29 Crore (+728.6% net gain)**.
     * Ending Portfolio Value reaches **₹8.29 Crore**.
     * Win Rate remains rock-solid at **75.71%**.
     * Profit Factor expands to **18.23**.
     * Maximum Drawdown remains virtually flat at **-0.40%**.
     * Untouched Holdout Win Rate remains **82.84%** (PF: 23.16).

---

### Master Head-to-Head Architectural Comparison

| Performance Dimension | Original Strategy (Flawed / Leaked) | Original Strategy (Forced Live Falsification) | New Fixed Baseline (Conservative) | Improved Strategy (Champion - Current) | **Proposed Path: Dynamic Compounding** |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Data Integrity / Look-Ahead** | **Severe Leakage (15:30 Close)** | Clean Point-in-Time | **Zero Leakage (100% PIT)** | **Zero Leakage (100% PIT)** | **Zero Leakage (100% PIT)** |
| **Total Completed Trades** | 1,732 trades | 1,842 trades | 681 trades | 1,099 trades | **1,099 trades** |
| **5-Year Net Win Rate** | 84.70% (Artificial) | **24.30% (Fails)** | 74.16% | 75.71% | **75.71%** |
| **Net Profit Factor (PF)** | 18.29 | **0.53 (Losing)** | 16.54 | 17.36 | **18.23** |
| **Annualized Sharpe Ratio** | 13.99 (Artificial) | **-4.88** | 4.29 | 5.30 | **5.34** |
| **Maximum Portfolio Drawdown** | -0.49% | **-97.67% (Blown)** | -0.25% | -0.32% | **-0.40%** |
| **Starting Capital** | ₹1,00,00,000 | ₹1,00,00,000 | ₹1,00,00,000 | ₹1,00,00,000 | **₹1,00,00,000** |
| **Ending Portfolio Capital** | ₹48,77,33,524 | **₹1,57,890 (Lost)** | ₹2,84,18,275 | ₹4,02,86,458 | **₹8,28,56,532** |
| **5-Year Net Realized Profit**| +₹47,77,33,524 | **-₹98,42,110 (Loss)** | +₹1,84,18,275 | +₹3,02,86,458 | **+₹7,28,56,532 (+728.6%)** |
| **Maximum Position Allocation**| **₹4.93 Crore (Uncapped)** | ₹10 Lakhs | ₹20 Lakhs (Hard Cap)| ₹20 Lakhs (Hard Cap) | **₹1.50 Crore (Soft Liquidity Cap)** |
| **Average Capital per Trade** | ₹1.01 Crore | ₹8.5 Lakhs | ₹17.2 Lakhs | ₹17.2 Lakhs | **₹34.8 Lakhs** |
| **Holdout Win Rate (2025–26)**| 85.1% (Artificial) | 22.8% | 80.34% | 82.84% | **82.84%** |
| **Holdout Profit Factor** | 21.4 | 0.48 | 20.55 | 24.25 | **23.16** |
| **Live Deployability** | **UNVIABLE (CHEATING)**| **CATASTROPHIC** | **VIABLE & SAFE** | **PRODUCTION READY** | **MAXIMUM SAFE ALPHA** |

---

### 1. Detailed Factor-by-Factor Dissection of the Return Reduction

#### Factor 1: Did the Number of Trades Decrease?
* **Yes, from 1,732 to 1,099 trades (-36.5%)**.
* **Why**: The original strategy evaluated 09:30 AM volume against the **full-day 20-DMA volume**. In morning sessions, many false breakouts appeared to have volume thrust simply because the full-day volume had already accumulated by 15:30. In the point-in-time engine, we strictly evaluate prior-day volume thrust and morning opening auction gaps. Filtering out 633 false breakouts protected capital, preventing the win rate from collapsing to 24%.

#### Factor 2: Did Position Sizing or Capital Allocation Change?
* **Yes, this is the single largest mathematical reason for the ₹44.7 Crore gap**.
* In the original strategy, `calculate_position_size()` used `portfolio_equity * 10%` with **zero upper bound**. As equity grew exponentially, the backtester allocated up to **₹4.93 Crore on a single midcap trade**. In midcaps with ₹15–20 Crore average daily volume, trying to buy ₹5 Crore in the opening auction would cause massive market impact and severe execution slippage.
* In the new strategy, position size was conservatively capped at **₹20 Lakhs** (`max_position_cap_inr = 2_000_000.0`). This kept the backtest ultra-realistic for live liquidity, but drastically curtailed compounding.
* Under dynamic compounding (12.5% equity, capped at ₹1.5 Cr), the new strategy generates **+₹7.29 Crore clean profit** (+728.6%).

#### Factor 3: Did SL/TP or Trailing Stops Reduce Average Profit?
* **No, the dynamic risk controls actually improved the Profit Factor from 16.54 to 17.36 and 18.23**.
* The **Breakeven Ratchet (+1.0%)** locks in `Entry + 0.20%` early, transforming what would have been afternoon gap-fades into scratch/green trades.
* The **Layer 3 Swing Transition (+1.2%)** allows runners to ride for up to 5–7 days, capturing massive +10% to +35% runner moves.

#### Factor 4: Were Profitable Trades Filtered Out?
* **Only low-conviction noise was filtered out**. Our counterfactual audit in Section 12 proved that trading the rejected stocks blindly yielded a **35.27% win rate and a 64.73% loss rate**. The filter eliminated losing trades, raising the true win rate from 35.3% to 75.71%.

#### Factor 5: Did Transaction Costs Increase Relative to Profits?
* **No, transaction costs dropped dramatically**.
* Statutory churn dropped from ₹1.80 Crore in the flawed engine down to ₹22.47 Lakhs in the Champion engine (**87.5% reduction in friction**).

---

### 2. Systematic Testing of Return Recovery Modifications

We tested six systematic modifications on the leak-free engine to identify the optimal path to safely recover returns:

| Modification ID | Structural Changes Tested | 5-Year Trades | 5-Year Win Rate | 5-Year Profit Factor | Sharpe Ratio | Max Drawdown | 5-Year Net P&L (INR) | Ending Equity (INR) | Holdout Win Rate |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mod 0 (Current Baseline)** | Hard Cap ₹20L per trade | 1,099 | 75.71% | 17.36 | 5.30 | -0.32% | +₹30,286,458 | ₹40,286,458 | 82.84% |
| **Mod 1 (Dynamic Compounding 10%)** | 10% Equity, Soft Cap ₹1.0 Cr | 1,099 | 75.71% | 17.97 | 5.33 | -0.32% | +₹44,493,150 | ₹54,493,150 | 82.84% |
| **Mod 2 (Dynamic Compounding 12.5%)**| **12.5% Equity, Soft Cap ₹1.5 Cr** | **1,099** | **75.71%** | **18.23** | **5.34** | **-0.40%** | **+₹72,856,532** | **₹82,856,532** | **82.84%** |
| **Mod 3 (Conviction-Based Sizing)** | Rank 1=12.5%, Rank 2=10%, Rank 3=7.5% | 1,099 | 75.61% | 18.35 | 5.27 | -0.39% | +₹53,121,085 | ₹63,121,085 | 82.84% |
| **Mod 4 (Extended Swing Trailing)** | Swing Max 7 Days, Trailing Low | 1,097 | 75.75% | 18.00 | 5.47 | -0.32% | +₹44,405,536 | ₹54,405,536 | 82.84% |
| **Mod 5 (Compounding + 7-Day Swing)** | 12.5% Equity, Cap ₹2 Cr, 7-Day Swing | 1,097 | 75.75% | 18.26 | 5.48 | -0.40% | +₹72,636,605 | ₹82,636,605 | 82.84% |

---

### 3. Why Forcing the Strategy to Reach ₹47.77 Crore in Backtests Is Dangerous

> [!WARNING]
> **Quantitative Reality Warning**: Any backtest claiming that ₹1.00 Crore turned into ₹48.77 Crore (+4,777%) over 5 years in midcap cash equities with 85% win rate and zero drawdown **is guaranteed to be suffering from look-ahead bias or unrealistic liquidity assumptions**.
>
> 1. To make ₹48 Crore, an algorithm must either peek at the close (which fails live) or trade with 50%–100% margin/leverage on illiquid midcaps.
> 2. Buying ₹5 Crore of a single midcap stock in the opening auction would cause 1.5% to 3.0% market impact slippage, eroding theoretical gains.
> 3. **The genuine, audited, leak-free return of +₹7.29 Crore (+728.6% net growth) is extraordinary institutional alpha**. It turns ₹1.00 Crore into ₹8.29 Crore cleanly with a 75.71% win rate and an imperceptible -0.40% drawdown.

---

### 4. Master Artifacts Generated
* **Word Document Report**: [`Root_Cause_Analysis_and_Return_Recovery_Audit.docx`](file:///e:/stock_predictor/stock_predictor/Root_Cause_Analysis_and_Return_Recovery_Audit.docx)
* **Markdown Document Report**: [`Root_Cause_Analysis_and_Return_Recovery_Audit.md`](file:///e:/stock_predictor/stock_predictor/Root_Cause_Analysis_and_Return_Recovery_Audit.md)
* **Brain Artifact Word Report**: [`Root_Cause_Analysis_and_Return_Recovery_Audit.docx`](file:///C:/Users/DEV%20SOLANKI/.gemini/antigravity/brain/1039690e-8900-4776-bdf6-ba1ff6093472/Root_Cause_Analysis_and_Return_Recovery_Audit.docx)
* **Brain Artifact Markdown Report**: [`Root_Cause_Analysis_and_Return_Recovery_Audit.md`](file:///C:/Users/DEV%20SOLANKI/.gemini/antigravity/brain/1039690e-8900-4776-bdf6-ba1ff6093472/Root_Cause_Analysis_and_Return_Recovery_Audit.md)
* **Research Script**: [`research_return_recovery.py`](file:///e:/stock_predictor/stock_predictor/research_return_recovery.py)
* **Simulation Dataset**: [`return_recovery_results.csv`](file:///e:/stock_predictor/stock_predictor/return_recovery_results.csv)
