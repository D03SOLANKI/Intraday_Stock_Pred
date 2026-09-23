# System Ruthless Forensic Audit & Failure Post-Mortem

**An Uncompromising, Evidence-Based Investigation of Code Deficiencies, Hardcoded Rules, Large-Cap Contamination, Selectivity Violations, Dormant Daemon Execution, and False AI Claims**

---

## 1. Confirmed System Bugs

| Bug ID | Subsystem & File Location | Defect Description | Exact Operational Consequence | Severity |
| :---: | :--- | :--- | :--- | :---: |
| **BUG-01** | `live_scanner.py`<br>`Line 151` | **Arbitrary Candidate Truncation via `.head(4)`**<br>Blindly sliced candidates instead of enforcing selectivity rules. | When 11 stocks qualified today, the system arbitrarily picked 4 instead of rejecting the day due to diffuse momentum. | **CRITICAL** |
| **BUG-02** | `live_scanner.py`<br>`Lines 18–33` | **Hardcoded Universe Contaminated with Large-Caps**<br>Bypassed `nifty_midcap_150.csv` using a static 27-ticker list. | `JINDALSTEL` and `INDUSTOWER` (Nifty 100 / Large-Caps) were selected, violating the Mid-Cap-only mandate. | **CRITICAL** |
| **BUG-03** | `order_manager.py`<br>`Missing Feature` | **Complete Absence of Portfolio-Level Take-Profit Logic**<br>No portfolio profit milestone monitoring. | Portfolio reached $+₹1,04,000$ unrealized gain, but the system lacked any rule to exit, eventually closing in a loss. | **CRITICAL** |
| **BUG-04** | `autonomous_trading_daemon.py`<br>`Lines 153–162` | **Dormant Intraday Monitoring Loop**<br>`time.sleep(30)` executed without polling live ticks. | Daemon never invoked `order_mgr.process_tick()` between 09:30 and 15:15 IST; trailing ratchets were completely blind. | **CRITICAL** |
| **BUG-05** | `autonomous_trading_daemon.py`<br>`Line 169` | **Hardcoded Entry-Price Exit at 15:15 IST**<br>`market_px = {p['symbol']: p['entry_price']}` | Falsified square-off exits at `entry * (1 - 0.002)`, reporting a synthetic -0.24% loss while ignoring real prices. | **CRITICAL** |

---

## 2. Comprehensive Hardcoded Logic Census

| File Name | Function / Scope | Line(s) | Hardcoded Value | Operational Justification | Audit Verdict & Mandatory Action |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `live_scanner.py` | Global | 18–22 | `CATALYST_SYMBOLS` (27 tickers) | Quick lookup list for live scanning. | **REMOVED**. Contained Large-Caps (`JINDALSTEL`, `INDUSTOWER`, `BHEL`, `DABUR`, `POLYCAB`). Replaced with dynamic CSV loader. |
| `dynamic_compounding_strategy.py` | `__init__` | 21 | `self.max_concurrent_positions = 4` | Assumed 4 slots for 28% sizing tier. | **REMOVED**. Changed to 2 positions max with strict rejection when candidates $> 2$. |
| `dynamic_compounding_strategy.py` | `__init__` | 44–48 | `self.catalyst_symbols` (27 tickers) | Added $+0.20$ score bias to selected tickers. | **REMOVED**. Subjective bias favoring arbitrary stocks. Replaced with pure objective volume thrust. |
| `live_scanner.py` | `run_scanner` | 151 | `eligible.head(strat.max_concurrent_positions)` | Slice top N ranked stocks. | **REMOVED**. Masked selectivity failures. Replaced with hard rejection if count $> 2$. |
| `autonomous_trading_daemon.py` | `run_daemon` | 169 | `market_px = {p['symbol']: p['entry_price']}` | Placeholder for EOD prices. | **REMOVED**. Falsified trade results. Replaced with live yfinance price polling at 15:15 IST. |
| `point_in_time_strategy.py` | `__init__` | 16 | `self.max_concurrent_positions = 5` | Legacy Candidate A position count. | **OBSOLETE**. Must not be referenced in production. |
| `improved_point_in_time_strategy.py`| `__init__` | 22 | `self.max_concurrent_positions = 8` | Candidate B expanded slots. | **OBSOLETE**. Violates 2-trade limit. |
| `order_manager.py` | `__init__` | 20 | `take_profit_pct = 0.040` | Only individual $+4.0\%$ target defined. | **UPGRADED**. Added `portfolio_take_profit_inr = 100_000.0` to lock aggregate gains. |

---

## 3. Exact Root Cause: 4-Stock Prediction

### 3.1 The Responsible Code
* `strategy/dynamic_compounding_strategy.py`, **Line 21**:
  ```python
  self.max_concurrent_positions = 4     # Max 4 concurrent slots
  ```
* `live_scanner.py`, **Line 151**:
  ```python
  top_candidates = eligible.head(strat.max_concurrent_positions).copy()
  ```

### 3.2 Dynamic vs. Hardcoded Reality
The prediction count was **100% HARDCODED** to 4 slots via `.head(4)`. It was **NOT** dynamically generated.

### 3.3 The Strategy Violation
In today's live market session (2026-09-23), **11 candidates met all entry criteria**.
When 11 stocks pass morning gap and coiling filters simultaneously, it indicates **broad market beta expansion** (an index-wide tide lifting all boats), not an isolated, high-conviction idiosyncratic top gainer. 
Instead of detecting this selectivity failure and rejecting the day, the code blindly sliced the top 4 stocks using `.head(4)`.

### 3.4 The Correct Enforced Rule
```python
MAX_ALLOWED_OPPORTUNITIES = 2
if len(eligible) == 0:
    return 0 trades (100% Cash)
elif len(eligible) > MAX_ALLOWED_OPPORTUNITIES:
    print(f"[REJECTED] {len(eligible)} opportunities qualify (> 2). Selectivity failure.")
    return 0 trades (Day completely rejected, 100% Cash preserved)
else:
    return eligible (Exactly 1 or 2 trades)
```
No `[:2]`. No `.head(2)`. The day is rejected.

---

## 4. Exact Root Cause: Large-Cap Predictions

### 4.1 The Responsible Code
* `live_scanner.py`, **Lines 18–22 and Lines 30–33**:
  ```python
  CATALYST_SYMBOLS = [
      'NIACL', 'GICRE', 'TATAINVEST', 'GVT&D', 'JSL', 'JINDALSTEL', 'BSE', 'IDEA', 'INDUSTOWER', 
      'APARINDS', 'RVNL', 'BHEL', 'WAAREEENER', 'PATANJALI', 'AWL', 'DABUR', 'POLYCAB', 'THERMAX', 
      'SUZLON', 'TATACOMM', 'VOLTAS', 'KPRMILL', 'POLICYBZR', 'SJVN', 'JUBLFOOD', 'HONAUT', 'GODREJIND'
  ]
  if symbols is None:
      symbols = CATALYST_SYMBOLS
  ```

### 4.2 The Mechanism of Contamination
`live_scanner.py` **never loaded `nifty_midcap_150.csv`**. Instead, it defaulted to `CATALYST_SYMBOLS`, a hardcoded list containing:
1. `JINDALSTEL` (Market Cap: ₹1,15,000+ Crores) — **NIFTY 100 / LARGE-CAP**. `JINDALSTEL` is not even in `nifty_midcap_150.csv`!
2. `INDUSTOWER` (Market Cap: ₹1,00,000+ Crores) — **NIFTY 100 / LARGE-CAP**.
3. `BHEL` (Market Cap: ₹1,40,000+ Crores) — **NIFTY 100 / LARGE-CAP**.

The system had **zero market-cap validation checks**, allowing Large-Caps to enter the candidate pool and take the #1 and #2 prediction spots.

### 4.3 The Correct Enforced Rule
1. Dynamically load from `nifty_midcap_150.csv`.
2. Cross-reference against `LARGE_CAP_EXCLUSIONS` (Top 100 companies).
3. If any Large-Cap appears, immediately purge it or raise a system failure error.

---

## 5. Exact Root Cause: Failure to Exit at ₹1,04,000 Profit

### 5.1 Was There a Rule Capable of Triggering the Exit?
**NO.** The system had **ZERO portfolio-level take-profit logic**.
* `DynamicCompoundingStrategy` only defined an individual per-stock target (`take_profit_pct = 0.040`). A stock had to rise $+4.0\%$ on its own to trigger an exit.
* There was no mechanism tracking aggregate portfolio P&L (e.g., $+₹1,00,000$ or $+1.0\%$ portfolio equity).

### 5.2 The Compounding Failure in the Daemon
In `autonomous_trading_daemon.py` (**Lines 153–162**), the intraday monitoring loop was completely dormant:
```python
if time_0930 <= curr_time < time_1515:
    logger.info(f"Intraday heartbeat [{curr_time.strftime('%H:%M:%S')} IST]: Tracking 4 positions...")
    time.sleep(30)
    continue
```
The daemon **never downloaded live price ticks** and **never called `order_mgr.process_tick()`**! Even if an individual stock had hit the $+4.0\%$ target, the daemon was completely blind to it.

### 5.3 The Falsified Square-Off Exit
At 15:15 IST (**Line 169**), the daemon executed:
```python
market_px = {p['symbol']: p['entry_price'] for p in order_mgr.positions}
summary_df = order_mgr.square_off_at_eod(market_px)
```
It passed `entry_price` as the current market price, forcing every position to exit at `entry_price * (1 - 0.002 slippage)`, generating a synthetic $-0.24\%$ loss while ignoring actual market gains!

### 5.4 The Correct Enforced Rule
1. Added `portfolio_profit_target_inr = 100_000.0`.
2. Added `process_portfolio_ticks(live_prices)` in `order_manager.py` that computes total portfolio unrealized P&L every 30 seconds.
3. If total P&L $\ge ₹1,00,000$, all positions are immediately squared off to lock profit.
4. Square-off at 15:15 IST downloads real market prices from yfinance.

---

## 6. Look-Ahead Bias & Data Leakage Audit

1. **Backtest Look-Ahead Leakage**:
   In `run_strategy_backtest.py` and `build_detailed_trades_dataset.py`, the original strategy screened at 09:30 AM using:
   $$\text{rng\_pos} = \frac{\text{Close}_{\text{EOD}} - \text{Low}_{\text{EOD}}}{\text{High}_{\text{EOD}} - \text{Low}_{\text{EOD}}} \ge 0.70$$
   In daily historical bars, `Close` is the 15:30 IST close! This leaked the end-of-day price 6 hours into the past, artificially generating an $84.7\%$ win rate. When forced point-in-time at 09:15 AM without future data, win rate collapsed to $24.3\%$.
2. **Static Survivorship Bias**:
   The backtests evaluated `nifty_midcap_150.csv` (a 2026 constituent list) retrospectively across 2021–2025, benefiting from survivorship bias by including multi-baggers that were small-caps in 2021.
3. **Live Scanner Indexing Vulnerability**:
   In `live_scanner.py`, `c_series.iloc[-2]` assumed the last bar was always the live bar. If executed on a weekend or post-market, `iloc[-2]` would fetch two days prior rather than yesterday's close.

---

## 7. Learning Reality: Is the System Actually Learning?

### Blunt Verdict: 100% HEURISTIC RULE-BASED. ZERO MACHINE LEARNING.
* The system is **NOT** learning, **NOT** adaptive, and **NOT** AI-driven.
* There is no neural network, no random forest, no reinforcement learning agent, and no Bayesian parameter updating in production.
* The "CRMV score" is a static linear equation with hand-tuned weights:
  $$\text{Score} = 0.50 \cdot \text{Gap} + 0.35 \cdot \text{Coiling} + 0.15 \cdot \text{Volume}$$
* Calling this system "AI-driven prediction" is factually inaccurate. It is an algorithmic rule-based screening script.

---

## 8. Verification Test Suite Results (13/13 Tests Passed)

All fixes were implemented and verified with a standalone test suite ([tests/test_audit_fixes.py](file:///e:/stock_predictor/stock_predictor/tests/test_audit_fixes.py)):

```
Ran 13 tests in 0.038s — OK (All Passed)
```

| Test # | Test Case Description | Verified Behavior | Status |
| :---: | :--- | :--- | :---: |
| **01** | 0 valid stocks | 0 trades generated; 100% Cash preserved. | **PASSED** |
| **02** | 1 valid stock | Exactly 1 trade placed. | **PASSED** |
| **03** | 2 valid stocks | Exactly 2 trades placed. | **PASSED** |
| **04** | 3 valid stocks | **REJECTED (0 trades)**. Selectivity rule strictly enforced; no `[:2]` slicing. | **PASSED** |
| **05** | 4+ valid stocks | **REJECTED (0 trades)**. Multi-opportunity day rejected as broad beta. | **PASSED** |
| **06** | Large-Caps mixed with Mid-Caps | `JINDALSTEL`, `INDUSTOWER`, `BHEL`, `POLYCAB` strictly purged. | **PASSED** |
| **07** | No valid Mid-Cap candidates | 0 trades placed; 100% Cash preserved. | **PASSED** |
| **08** | Portfolio profit target reached | Total P&L reaches $+₹1,08,000 \ge ₹1,00,000$; **all positions squared off instantly**. | **PASSED** |
| **09** | Portfolio profit target not reached | Total P&L $< ₹1,00,000$; positions remain open with trailing ratchet. | **PASSED** |
| **10** | Multiple positions tracking | Aggregate unrealized P&L computed accurately across concurrent trades. | **PASSED** |
| **11** | Exit signal generation | Hard stop loss triggers immediately upon price drop; position closed. | **PASSED** |
| **12** | Exit execution failure | Missing broker price handled gracefully without crash. | **PASSED** |
| **13** | Missing/stale order CSV | Missing files handled safely with zero unhandled exceptions. | **PASSED** |
