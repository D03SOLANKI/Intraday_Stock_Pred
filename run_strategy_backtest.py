import pandas as pd
import numpy as np
from strategy.backtester import BacktestEngine
from config import strategy_config as cfg

def main():
    print('Loading 1-year historical dataset...')
    all_df = pd.read_pickle('all_midcap_stock_days_1year.pkl')
    top5_df = pd.read_csv('top5_daily_enriched.csv')
    
    engine = BacktestEngine(all_df, top5_df)
    results = engine.run()
    
    print('\n' + '='*65)
    print('SYSTEMATIC MID-CAP TOP-GAINER STRATEGY BACKTEST RESULTS' )
    print('='*65)
    print(f'Initial Portfolio Equity:   INR {results["initial_equity"]:,.2f}')
    print(f'Final Portfolio Equity:     INR {results["final_equity"]:,.2f}')
    print(f'Net Total Return:           {results['net_return_pct']:+.2f}%')
    print(f'Total Executed Trades:      {results["total_trades"]}')
    print(f'Win Rate:                  {results["win_rate_pct"]:.2f}%')
    print(f'Profit Factor:              {results["profit_factor"]:.2f}')
    print(f'Annualized Sharpe Ratio:    {results["sharpe_ratio"]:.2f}')
    print(f'Maximum Drawdown:           {results["max_drawdown_pct"]:.2f}%')
    print('='*65)
    
    t_df = results['trades_df']
    t_df.to_csv('strategy_backtest_trades.csv', index=False)
    print('All trades saved to strategy_backtest_trades.csv')

if __name__ == '__main__':
    main()
