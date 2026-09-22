import os
import sys
import time
import math
import json
import numpy as np
import pandas as pd
from scipy import stats
import shutil

from config import strategy_config as cfg
from strategy.rules import check_volume_trap_exclusion
from strategy.position_sizer import calculate_initial_stop_loss, calculate_position_size

def wilson_score_interval(successes, total, confidence=0.95):
    if total == 0:
        return 0.0, 0.0, 0.0
    p_hat = successes / total
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denominator = 1 + z**2 / total
    centre_adjusted_probability = p_hat + z**2 / (2 * total)
    adjusted_standard_deviation = math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)
    lower_bound = (centre_adjusted_probability - z * adjusted_standard_deviation) / denominator
    upper_bound = (centre_adjusted_probability + z * adjusted_standard_deviation) / denominator
    return p_hat * 100.0, max(0.0, lower_bound * 100.0), min(100.0, upper_bound * 100.0)

def simulate_strategy_slice(
    all_df,
    date_slice,
    vol_ratio_threshold=1.60,
    headwind_threshold=-0.005,
    coiling_proximity=0.03,
    rsi_min=35.0,
    rsi_max=65.0,
    max_positions=5,
    initial_equity=10_000_000.0
):
    """
    Fast systematic simulator for a given slice of dates and parameter settings.
    Deducts all statutory taxes and execution slippage strictly point-in-time.
    """
    dates = sorted(date_slice)
    equity = initial_equity
    active_positions = []
    completed_trades = []
    daily_equity = []
    
    # Filter dataframe for dates
    df_slice = all_df[all_df['date'].isin(dates)]
    grouped_by_date = {d: group for d, group in df_slice.groupby('date')}
    
    for d in dates:
        day_df = grouped_by_date.get(d)
        if day_df is None or day_df.empty:
            daily_equity.append({'date': d, 'equity': equity})
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
            
            # Check trailing stop
            if curr_low <= pos['trailing_stop']:
                exit_price = pos['trailing_stop'] * 0.998 # 0.20% execution slippage
                buy_val = pos['entry_price'] * pos['shares']
                sell_val = exit_price * pos['shares']
                gross_pnl = sell_val - buy_val
                
                # Statutory friction (delivery swing)
                brokerage = 0.0
                stt = (buy_val + sell_val) * 0.001
                exch = (buy_val + sell_val) * 0.0000297
                stamp = buy_val * 0.00015
                sebi = (buy_val + sell_val) * 0.000001
                gst = 0.18 * (brokerage + exch + sebi)
                dp = 15.93
                charges = brokerage + stt + exch + stamp + sebi + gst + dp
                net_pnl = gross_pnl - charges
                
                equity += net_pnl
                completed_trades.append({
                    'trading_date': pos['entry_date'],
                    'exit_date': d,
                    'symbol': sym,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'charges': charges,
                    'return_pct': (net_pnl / buy_val) * 100.0,
                    'is_win': net_pnl > 0,
                    'trade_type': 'SWING'
                })
                continue
                
            # Max holding days reached
            if pos['days_held'] >= cfg.SWING_MAX_HOLDING_DAYS:
                exit_price = curr_close * 0.998
                buy_val = pos['entry_price'] * pos['shares']
                sell_val = exit_price * pos['shares']
                gross_pnl = sell_val - buy_val
                
                brokerage = 0.0
                stt = (buy_val + sell_val) * 0.001
                exch = (buy_val + sell_val) * 0.0000297
                stamp = buy_val * 0.00015
                sebi = (buy_val + sell_val) * 0.000001
                gst = 0.18 * (brokerage + exch + sebi)
                dp = 15.93
                charges = brokerage + stt + exch + stamp + sebi + gst + dp
                net_pnl = gross_pnl - charges
                
                equity += net_pnl
                completed_trades.append({
                    'trading_date': pos['entry_date'],
                    'exit_date': d,
                    'symbol': sym,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'charges': charges,
                    'return_pct': (net_pnl / buy_val) * 100.0,
                    'is_win': net_pnl > 0,
                    'trade_type': 'SWING'
                })
                continue
                
            pos['trailing_stop'] = max(pos['trailing_stop'], row['low'])
            retained.append(pos)
            
        active_positions = retained
        
        # Benchmark Headwind Protection Gate
        if headwind_threshold is not None and midcap_ret < headwind_threshold:
            daily_equity.append({'date': d, 'equity': equity})
            continue
            
        # 2. Layer 1 Pre-market screening
        l1_cands = []
        for _, row in day_df.iterrows():
            dist_sma = abs(row['dist_sma20']) / 100.0 if pd.notnull(row['dist_sma20']) else 0.5
            rsi_prev = row['rsi_prev'] if pd.notnull(row['rsi_prev']) else 50.0
            if dist_sma <= coiling_proximity and (rsi_min <= rsi_prev <= rsi_max):
                l1_cands.append(row)
                
        # 3. Layer 2 Intraday Entry
        for cand in l1_cands:
            if len(active_positions) >= max_positions:
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
            if vol_ratio < vol_ratio_threshold:
                continue
                
            range_pos = cand['rng_pos'] if pd.notnull(cand['rng_pos']) else 0.5
            if check_volume_trap_exclusion(vol_ratio, range_pos):
                continue
                
            entry_price = open_price * 1.003 # 0.3% entry slippage
            session_low = cand['low']
            session_high = cand['high']
            session_close = cand['close']
            
            initial_sl = entry_price * 0.98 # -2.0% stop
            pos_capital = min(equity * cfg.MAX_POSITION_WEIGHT_PCT, 2_000_000.0)
            shares = int(pos_capital / entry_price)
            if shares <= 0:
                continue
                
            buy_val = entry_price * shares
            
            # Intraday Stop Loss hit check
            if session_low <= initial_sl:
                exit_price = initial_sl * 0.998
                sell_val = exit_price * shares
                gross_pnl = sell_val - buy_val
                
                brokerage = min(20.0, buy_val * 0.0003) + min(20.0, sell_val * 0.0003)
                stt = sell_val * 0.00025
                exch = (buy_val + sell_val) * 0.0000297
                stamp = buy_val * 0.00003
                sebi = (buy_val + sell_val) * 0.000001
                gst = 0.18 * (brokerage + exch + sebi)
                charges = brokerage + stt + exch + stamp + sebi + gst
                net_pnl = gross_pnl - charges
                
                equity += net_pnl
                completed_trades.append({
                    'trading_date': d,
                    'exit_date': d,
                    'symbol': sym,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'charges': charges,
                    'return_pct': (net_pnl / buy_val) * 100.0,
                    'is_win': net_pnl > 0,
                    'trade_type': 'INTRADAY'
                })
                continue
                
            # Layer 3 Persistence check (Swing Qualification)
            is_swing = (range_pos >= cfg.RANGE_POS_MIN_L3) and (vol_ratio >= cfg.VOL_RATIO_MIN_L3)
            
            if is_swing:
                active_positions.append({
                    'symbol': sym,
                    'entry_date': d,
                    'entry_price': entry_price,
                    'shares': shares,
                    'allocated_capital': buy_val,
                    'trailing_stop': session_low,
                    'days_held': 1,
                    'is_swing': True
                })
            else:
                # Intraday square-off at close
                exit_price = session_close * 0.998
                sell_val = exit_price * shares
                gross_pnl = sell_val - buy_val
                
                brokerage = min(20.0, buy_val * 0.0003) + min(20.0, sell_val * 0.0003)
                stt = sell_val * 0.00025
                exch = (buy_val + sell_val) * 0.0000297
                stamp = buy_val * 0.00003
                sebi = (buy_val + sell_val) * 0.000001
                gst = 0.18 * (brokerage + exch + sebi)
                charges = brokerage + stt + exch + stamp + sebi + gst
                net_pnl = gross_pnl - charges
                
                equity += net_pnl
                completed_trades.append({
                    'trading_date': d,
                    'exit_date': d,
                    'symbol': sym,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'charges': charges,
                    'return_pct': (net_pnl / buy_val) * 100.0,
                    'is_win': net_pnl > 0,
                    'trade_type': 'INTRADAY'
                })
                
        daily_equity.append({'date': d, 'equity': equity})
        
    trades_df = pd.DataFrame(completed_trades)
    eq_df = pd.DataFrame(daily_equity)
    
    # Compute summary performance metrics
    total_trades = len(trades_df)
    if total_trades == 0:
        return {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'ci_lower': 0.0, 'ci_upper': 0.0, 'net_pnl': 0.0, 'return_pct': 0.0,
            'avg_trade_pct': 0.0, 'std_trade_pct': 0.0, 'profit_factor': 0.0,
            'max_drawdown': 0.0, 'sharpe_ratio': 0.0, 'trades_df': trades_df,
            'equity_df': eq_df
        }
        
    wins = (trades_df['net_pnl'] > 0).sum()
    losses = (trades_df['net_pnl'] <= 0).sum()
    wr, ci_low, ci_high = wilson_score_interval(wins, total_trades)
    
    net_pnl = trades_df['net_pnl'].sum()
    ret_pct = (net_pnl / initial_equity) * 100.0
    
    gross_wins = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
    gross_loss = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum())
    pf = (gross_wins / gross_loss) if gross_loss > 0 else 99.99
    
    avg_trade_pct = trades_df['return_pct'].mean()
    std_trade_pct = trades_df['return_pct'].std() if total_trades > 1 else 1e-6
    
    # Daily returns Sharpe & Max Drawdown
    eq_df['daily_return'] = eq_df['equity'].pct_change().fillna(0.0)
    mean_daily = eq_df['daily_return'].mean()
    std_daily = eq_df['daily_return'].std() if len(eq_df) > 1 else 1e-6
    rf_daily = 0.06 / 252.0
    sharpe = ((mean_daily - rf_daily) / std_daily) * math.sqrt(252) if std_daily > 1e-6 else 0.0
    
    eq_df['peak'] = eq_df['equity'].cummax()
    eq_df['drawdown'] = (eq_df['equity'] - eq_df['peak']) / eq_df['peak']
    max_dd = eq_df['drawdown'].min() * 100.0
    
    return {
        'total_trades': total_trades,
        'wins': int(wins),
        'losses': int(losses),
        'win_rate': wr,
        'ci_lower': ci_low,
        'ci_upper': ci_high,
        'net_pnl': net_pnl,
        'return_pct': ret_pct,
        'avg_trade_pct': avg_trade_pct,
        'std_trade_pct': std_trade_pct,
        'profit_factor': pf,
        'max_drawdown': max_dd,
        'sharpe_ratio': max(0.0, sharpe),
        'trades_df': trades_df,
        'equity_df': eq_df
    }

def compute_deflated_sharpe_ratio(estimated_sharpe, var_sharpe, nb_trials, skewness, kurtosis, n_samples):
    """
    Computes Bailey & López de Prado (2014) Deflated Sharpe Ratio.
    Adjusts for multiple testing across nb_trials and non-normal return distributions.
    """
    if var_sharpe <= 0 or n_samples <= 1:
        return 0.50
    # Expected maximum Sharpe ratio under null hypothesis
    euler_mascheroni = 0.5772156649
    if nb_trials > 1:
        expected_max_sr = (1 - euler_mascheroni) * stats.norm.ppf(1 - 1.0 / nb_trials) + euler_mascheroni * stats.norm.ppf(1 - 1.0 / (nb_trials * math.e))
    else:
        expected_max_sr = 0.0
        
    sr_std = math.sqrt((1 - skewness * estimated_sharpe + ((kurtosis - 1) / 4.0) * estimated_sharpe**2) / (n_samples - 1))
    if sr_std <= 0:
        return 1.0
    z_stat = (estimated_sharpe - expected_max_sr) / sr_std
    dsr = stats.norm.cdf(z_stat)
    return dsr

def run_bootstrap_test(returns_base, returns_mod, n_iter=10000):
    """
    10,000 iteration bootstrap test for difference in means and Sharpe ratios.
    """
    np.random.seed(42)
    n_b = len(returns_base)
    n_m = len(returns_mod)
    
    if n_b < 5 or n_m < 5:
        return 0.0, 0.0, 0.0, 1.0
        
    diff_means = []
    diff_sharpes = []
    
    for _ in range(n_iter):
        boot_b = np.random.choice(returns_base, size=n_b, replace=True)
        boot_m = np.random.choice(returns_mod, size=n_m, replace=True)
        
        m_b = np.mean(boot_b)
        m_m = np.mean(boot_m)
        diff_means.append(m_m - m_b)
        
        s_b = np.std(boot_b) + 1e-9
        s_m = np.std(boot_m) + 1e-9
        diff_sharpes.append((m_m / s_m) - (m_b / s_b))
        
    diff_means = np.array(diff_means)
    diff_sharpes = np.array(diff_sharpes)
    
    ci_mean_low = np.percentile(diff_means, 2.5)
    ci_mean_high = np.percentile(diff_means, 97.5)
    obs_diff = np.mean(returns_mod) - np.mean(returns_base)
    
    # p-value: proportion of bootstrap differences <= 0
    p_boot = np.mean(diff_means <= 0)
    
    return obs_diff, ci_mean_low, ci_mean_high, p_boot

print("Validation framework module successfully loaded.")
