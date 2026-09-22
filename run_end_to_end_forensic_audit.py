import os
import sys
import pickle
import numpy as np
import pandas as pd
from scipy import stats

def run_forensic_audit():
    print("Loading datasets for independent forensic audit...")
    trades_path = "improved_stock_by_stock_5year_detailed.pkl"
    if not os.path.exists(trades_path):
        raise FileNotFoundError(f"{trades_path} not found")
    
    df_trades = pd.read_pickle(trades_path)
    print(f"Loaded {len(df_trades)} improved trades.")

    total_trades = len(df_trades)
    rank1_hits = int((df_trades['actual_universe_rank'] == 1).sum())
    top5_hits = int((df_trades['actual_universe_rank'] <= 5).sum())
    top10_hits = int((df_trades['actual_universe_rank'] <= 10).sum())
    top20_hits = int((df_trades['actual_universe_rank'] <= 20).sum())
    
    acc_rank1 = rank1_hits / total_trades
    acc_top5 = top5_hits / total_trades
    acc_top10 = top10_hits / total_trades
    acc_top20 = top20_hits / total_trades

    avg_actual_rank = float(df_trades['actual_universe_rank'].mean())
    median_actual_rank = float(df_trades['actual_universe_rank'].median())

    # Random Baseline comparison (Universe size = 150)
    random_rank1 = 1 / 150.0
    random_top5 = 5 / 150.0
    random_top10 = 10 / 150.0
    random_top20 = 20 / 150.0

    edge_rank1 = acc_rank1 / random_rank1
    edge_top5 = acc_top5 / random_top5
    edge_top10 = acc_top10 / random_top10
    edge_top20 = acc_top20 / random_top20

    tp = top10_hits
    fp = total_trades - top10_hits
    precision_top10 = tp / (tp + fp)

    returns = df_trades['return_pct'].values
    t_stat, p_val_t = stats.ttest_1samp(returns, 0.0)
    w_stat, p_val_w = stats.wilcoxon(returns)

    np.random.seed(42)
    n_boot = 10000
    boot_win_rates = []
    boot_mean_returns = []
    is_win_arr = df_trades['is_win'].values.astype(int)
    n = len(df_trades)

    for _ in range(n_boot):
        idx = np.random.randint(0, n, n)
        boot_win_rates.append(is_win_arr[idx].mean())
        boot_mean_returns.append(returns[idx].mean())

    ci_win_rate = (float(np.percentile(boot_win_rates, 2.5)), float(np.percentile(boot_win_rates, 97.5)))
    ci_mean_return = (float(np.percentile(boot_mean_returns, 2.5)), float(np.percentile(boot_mean_returns, 97.5)))

    ann_sharpe = float((np.mean(returns) / np.std(returns)) * np.sqrt(252 * (total_trades / 1241.0)))
    skew = float(stats.skew(returns))
    kurt = float(stats.kurtosis(returns))

    wins = df_trades[df_trades['is_win'] == True]
    losses = df_trades[df_trades['is_win'] == False]
    n_wins = int(len(wins))
    n_losses = int(len(losses))
    win_rate = float(n_wins / total_trades)

    avg_win = float(wins['return_pct'].mean())
    avg_loss = float(losses['return_pct'].mean())
    payoff_ratio = float(abs(avg_win / avg_loss)) if avg_loss != 0 else 0.0

    gross_pnl = float(df_trades['gross_pnl_inr'].sum())
    total_costs = float(df_trades['costs_inr'].sum())
    net_pnl = float(df_trades['net_pnl_inr'].sum())

    gross_win_sum = float(wins['gross_pnl_inr'].sum())
    gross_loss_sum = float(abs(losses['gross_pnl_inr'].sum()))
    profit_factor = float(gross_win_sum / gross_loss_sum) if gross_loss_sum > 0 else np.nan

    win_loss_seq = df_trades['is_win'].tolist()
    max_win_streak = 0
    max_loss_streak = 0
    curr_win_streak = 0
    curr_loss_streak = 0

    for w in win_loss_seq:
        if w:
            curr_win_streak += 1
            curr_loss_streak = 0
            if curr_win_streak > max_win_streak:
                max_win_streak = curr_win_streak
        else:
            curr_loss_streak += 1
            curr_win_streak = 0
            if curr_loss_streak > max_loss_streak:
                max_loss_streak = curr_loss_streak

    cum_pnl = np.cumsum(df_trades['net_pnl_inr'].values)
    initial_equity = 10000000.0
    equity_curve = initial_equity + cum_pnl
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - running_max) / running_max
    max_drawdown_pct = float(drawdowns.min() * 100.0)
    recovery_factor = float(net_pnl / abs(drawdowns.min() * initial_equity)) if drawdowns.min() != 0 else np.nan

    failure_counts = {
        "Opening Gap-Fill Trap / Instant Reversal": 0,
        "Midday Fade / Failed TP Expansion": 0,
        "Square-off Drag (Intraday Chop)": 0,
        "Full Stop Loss Hit (-1.8% to -2.0%)": 0
    }
    for _, row in losses.iterrows():
        sl_type = str(row['sl_or_tp_hit']).upper()
        mae = abs(row['mae_pct'])
        mfe = row['mfe_pct']
        if "STOP LOSS" in sl_type or mae >= 1.8:
            failure_counts["Full Stop Loss Hit (-1.8% to -2.0%)"] += 1
        elif mfe >= 0.8:
            failure_counts["Midday Fade / Failed TP Expansion"] += 1
        elif "INTRADAY" in sl_type or "SQUARE" in sl_type:
            failure_counts["Square-off Drag (Intraday Chop)"] += 1
        else:
            failure_counts["Opening Gap-Fill Trap / Instant Reversal"] += 1

    df_trades['trading_date_dt'] = pd.to_datetime(df_trades['trading_date'])
    yearly = {}
    for yr in [2021, 2022, 2023, 2024, 2025, 2026]:
        sub = df_trades[df_trades['trading_date_dt'].dt.year == yr]
        if len(sub) > 0:
            sub_wins = (sub['is_win'] == True).sum()
            yearly[yr] = {
                "trades": int(len(sub)),
                "win_rate": float(sub_wins / len(sub) * 100.0),
                "net_pnl": float(sub['net_pnl_inr'].sum()),
                "avg_return": float(sub['return_pct'].mean()),
                "profit_factor": float(sub[sub['is_win']]['gross_pnl_inr'].sum() / abs(sub[~sub['is_win']]['gross_pnl_inr'].sum())) if len(sub[~sub['is_win']]) > 0 else np.nan
            }

    holdout = df_trades[df_trades['trading_date_dt'] >= '2025-01-01']
    insample = df_trades[df_trades['trading_date_dt'] < '2025-01-01']

    slippage_tests = {}
    for slip in [0.001, 0.002, 0.004, 0.006, 0.008, 0.010]:
        slip_diff = slip - 0.004
        adj_returns = returns - (slip_diff * 100.0)
        adj_wins = int((adj_returns > 0).sum())
        adj_net_pnl = df_trades['capital_allocated'] * (adj_returns / 100.0) - df_trades['costs_inr']
        slippage_tests[f"{slip*100:.1f}%"] = {
            "win_rate": float(adj_wins / total_trades * 100.0),
            "net_pnl": float(adj_net_pnl.sum()),
            "avg_return": float(adj_returns.mean())
        }

    audit_summary = {
        "total_trades": total_trades,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": float(win_rate * 100.0),
        "ci_win_rate": (ci_win_rate[0]*100, ci_win_rate[1]*100),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff_ratio,
        "gross_pnl": gross_pnl,
        "total_costs": total_costs,
        "net_pnl": net_pnl,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "recovery_factor": recovery_factor,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "t_stat": float(t_stat),
        "p_val_t": float(p_val_t),
        "p_val_w": float(p_val_w),
        "ci_mean_return": ci_mean_return,
        "skewness": skew,
        "kurtosis": kurt,
        "ann_sharpe": ann_sharpe,
        "acc_rank1": float(acc_rank1 * 100.0),
        "acc_top5": float(acc_top5 * 100.0),
        "acc_top10": float(acc_top10 * 100.0),
        "acc_top20": float(acc_top20 * 100.0),
        "edge_rank1": float(edge_rank1),
        "edge_top5": float(edge_top5),
        "edge_top10": float(edge_top10),
        "edge_top20": float(edge_top20),
        "avg_actual_rank": avg_actual_rank,
        "median_actual_rank": median_actual_rank,
        "precision_top10": float(precision_top10 * 100.0),
        "failure_counts": failure_counts,
        "yearly": yearly,
        "insample_trades": int(len(insample)),
        "insample_win_rate": float((insample['is_win'].sum() / len(insample)) * 100.0),
        "insample_net_pnl": float(insample['net_pnl_inr'].sum()),
        "holdout_trades": int(len(holdout)),
        "holdout_win_rate": float((holdout['is_win'].sum() / len(holdout)) * 100.0),
        "holdout_net_pnl": float(holdout['net_pnl_inr'].sum()),
        "holdout_profit_factor": float(holdout[holdout['is_win']]['gross_pnl_inr'].sum() / abs(holdout[~holdout['is_win']]['gross_pnl_inr'].sum())),
        "slippage_tests": slippage_tests
    }

    with open("forensic_audit_results.pkl", "wb") as f:
        pickle.dump(audit_summary, f)

    print("FORENSIC AUDIT COMPLETED SUCCESSFULLY!")
    print(f"Total Trades: {total_trades}")
    print(f"Net Win Rate: {win_rate*100:.2f}% (95% CI: [{ci_win_rate[0]*100:.2f}%, {ci_win_rate[1]*100:.2f}%])")
    print(f"t-statistic: {t_stat:.4f} | p-value: {p_val_t:.2e}")
    print(f"Gross P&L: Rs. {gross_pnl:,.2f} | Net P&L: Rs. {net_pnl:,.2f} | Costs: Rs. {total_costs:,.2f}")
    print(f"Rank #1 Edge: {edge_rank1:.1f}x | Top 5 Edge: {edge_top5:.1f}x | Top 10 Edge: {edge_top10:.1f}x")
    print(f"Holdout Win Rate: {audit_summary['holdout_win_rate']:.2f}% | Holdout PnL: Rs. {audit_summary['holdout_net_pnl']:,.2f}")

if __name__ == "__main__":
    run_forensic_audit()
