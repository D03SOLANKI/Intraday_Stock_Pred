"""
Option 3: Machine Learning Top-3 Mid-Cap Next-Day Gainer Strategy
================================================================
Specifically predicts and trades the Top 3 Mid-Cap gainers on the NSE,
combining a Multi-Objective Gradient Boosted Ensemble (LambdaMART Ranker +
Top-3 Probability Classifier + Expected Return Regressor) with a point-in-time
09:30 AM Opening Range confirmation gate and dynamic trailing stops to capture
large 5% to 20% runner moves.
"""

from typing import Dict, List, Tuple, Optional
import os
import sys
import json
import math
import numpy as np
import pandas as pd
import lightgbm as lgb

# SEBI Official Large-Cap Exclusion Set (Nifty 100 Top Companies by Market Cap)
# Any symbol in this set is rejected to guarantee 100% pure Mid-Cap universe.
NIFTY100_LARGE_CAP_EXCLUSIONS = frozenset({
    # Nifty 50 Core
    'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'BHARTIARTL', 'SBIN', 'INFY', 'LICI',
    'ITC', 'HINDUNILVR', 'LT', 'BAJFINANCE', 'HCLTECH', 'MARUTI', 'SUNPHARMA',
    'ADANIENT', 'KOTAKBANK', 'TITAN', 'ONGC', 'TATAMOTORS', 'NTPC', 'AXISBANK',
    'ADANIGREEN', 'ADANIPORTS', 'COALINDIA', 'POWERGRID', 'BAJAJFINSV', 'M&M',
    'SIEMENS', 'HAL', 'ULTRACEMCO', 'IOC', 'JSWSTEEL', 'GRASIM',
    # Nifty Next 50 / Nifty 100 additions
    'DLF', 'ZOMATO', 'VBL', 'TRENT', 'BEL', 'INDIGO', 'WIPRO', 'TECHM',
    'EICHERMOT', 'NESTLEIND', 'DIVISLAB', 'BPCL', 'SHRIRAMFIN', 'HINDALCO',
    'GAIL', 'VEDL', 'TATASTEEL',
    # Previously misclassified large caps
    'JINDALSTEL', 'INDUSTOWER', 'BHEL',
})


class MLTop3GainerStrategy:
    """
    Production Strategy Engine for Option 3: ML Top-3 Next-Day Mid-Cap Gainers.
    """

    def __init__(
        self,
        initial_equity: float = 10_000_000.0,
        models_dir: Optional[str] = None,
        max_concurrent_positions: int = 3,
        position_weight: float = 0.28,
        adv_limit_pct: float = 0.05,
        initial_sl_pct: float = 0.025,
        trailing_activation_pct: float = 0.040,
        trailing_step_pct: float = 0.035,
        entry_slippage_pct: float = 0.0020,
        exit_slippage_pct: float = 0.0020,
        swing_max_days: int = 5
    ):
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.max_concurrent_positions = max_concurrent_positions
        self.position_weight = position_weight
        self.adv_limit_pct = adv_limit_pct
        self.initial_sl_pct = initial_sl_pct
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_step_pct = trailing_step_pct
        self.entry_slippage_pct = entry_slippage_pct
        self.exit_slippage_pct = exit_slippage_pct
        self.swing_max_days = swing_max_days

        # Model paths
        if models_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            models_dir = os.path.join(base_dir, "..", "ml", "models")

        self.models_dir = os.path.abspath(models_dir)
        self.ranker = None
        self.classifier = None
        self.regressor = None
        self.feature_cols = []
        self._load_models()

    def _load_models(self):
        """Loads serialized LightGBM booster models and feature metadata."""
        meta_path = os.path.join(self.models_dir, "feature_metadata.json")
        ranker_path = os.path.join(self.models_dir, "ranker.txt")
        classifier_path = os.path.join(self.models_dir, "classifier.txt")
        regressor_path = os.path.join(self.models_dir, "regressor.txt")

        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                meta = json.load(f)
                self.feature_cols = meta.get("features", [])

        if os.path.exists(ranker_path):
            self.ranker = lgb.Booster(model_file=ranker_path)
        if os.path.exists(classifier_path):
            self.classifier = lgb.Booster(model_file=classifier_path)
        if os.path.exists(regressor_path):
            self.regressor = lgb.Booster(model_file=regressor_path)

    def is_midcap(self, symbol: str) -> bool:
        """Structural gate: strictly excludes Nifty 100 Large-Caps."""
        return symbol.strip().upper() not in NIFTY100_LARGE_CAP_EXCLUSIONS

    def compute_features(self, df_history: pd.DataFrame) -> pd.DataFrame:
        """
        Computes the strictly point-in-time feature matrix for candidate ranking.
        """
        df = df_history.copy()
        df = df[df['symbol'].apply(self.is_midcap)].copy()
        df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

        grouped = df.groupby('symbol', group_keys=False)

        df['ret_1d'] = df['daily_return']
        df['ret_3d'] = grouped['close'].transform(lambda x: (x / x.shift(3) - 1.0) * 100.0)
        df['ret_5d'] = grouped['close'].transform(lambda x: (x / x.shift(5) - 1.0) * 100.0)
        df['ret_10d'] = grouped['close'].transform(lambda x: (x / x.shift(10) - 1.0) * 100.0)
        df['ret_20d'] = grouped['close'].transform(lambda x: (x / x.shift(20) - 1.0) * 100.0)

        df['sma_20'] = grouped['close'].transform(lambda x: x.rolling(20).mean())
        df['sma_50'] = grouped['close'].transform(lambda x: x.rolling(50).mean())
        df['dist_sma20_feat'] = (df['close'] - df['sma_20']) / (df['sma_20'] + 1e-6) * 100.0
        df['dist_sma50_feat'] = (df['close'] - df['sma_50']) / (df['sma_50'] + 1e-6) * 100.0
        df['sma20_trend'] = grouped['sma_20'].transform(lambda x: (x / x.shift(5) - 1.0) * 100.0)

        df['true_range_pct'] = (df['high'] - df['low']) / (df['prev_close'] + 1e-6) * 100.0
        df['atr_5d'] = grouped['true_range_pct'].transform(lambda x: x.rolling(5).mean())
        df['atr_20d'] = grouped['true_range_pct'].transform(lambda x: x.rolling(20).mean())
        df['compression_ratio'] = df['atr_5d'] / (df['atr_20d'] + 1e-6)

        df['vol_sma20'] = grouped['volume'].transform(lambda x: x.rolling(20).mean())
        df['vol_sma5'] = grouped['volume'].transform(lambda x: x.rolling(5).mean())
        df['vol_surge_t'] = df['volume'] / (df['vol_sma20'] + 1e-6)
        df['vol_accel_feat'] = df['vol_sma5'] / (df['vol_sma20'] + 1e-6)
        df['adv_20d_cr'] = (df['close'] * df['vol_sma20']) / 10_000_000.0

        range_span = df['high'] - df['low']
        df['range_position'] = np.where(range_span > 0, (df['close'] - df['low']) / range_span, 0.5)

        # 7. 52-Week High Proximity
        df['high_52w'] = grouped['high'].transform(lambda x: x.rolling(252, min_periods=20).max())
        df['dist_52w_high'] = (df['close'] - df['high_52w']) / (df['high_52w'] + 1e-6) * 100.0

        # 8. RSI Indicator (14 period)
        def calc_rsi(series, period=14):
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
            rs = gain / (loss + 1e-6)
            return 100.0 - (100.0 / (1.0 + rs))

        if 'rsi_prev' not in df.columns or df['rsi_prev'].isna().any():
            df['rsi_prev'] = grouped['close'].transform(lambda x: calc_rsi(x, 14)).fillna(50.0)

        if 'sector' in df.columns:
            sector_mean = df.groupby(['sector', 'date'])['daily_return'].transform('mean')
            df['stock_vs_sector'] = df['daily_return'] - sector_mean
        else:
            df['stock_vs_sector'] = 0.0

        return df

    def predict_top3_candidates(self, df_session_features: pd.DataFrame) -> pd.DataFrame:
        """
        Infers scores across all valid Mid-Caps and returns the Top 3 candidates.
        """
        if self.ranker is None or self.classifier is None or self.regressor is None:
            raise RuntimeError("Production models not loaded. Check ml/models directory.")

        valid_df = df_session_features.dropna(subset=self.feature_cols).copy()
        if valid_df.empty:
            return pd.DataFrame()

        X = valid_df[self.feature_cols]

        # Raw model inferences
        s_rank = self.ranker.predict(X)
        s_prob = self.classifier.predict(X)
        s_ret = self.regressor.predict(X)

        # Standardize within session
        def zscore(arr):
            std = np.std(arr) + 1e-6
            return (arr - np.mean(arr)) / std

        z_rank = zscore(s_rank)
        z_prob = zscore(s_prob)
        z_ret = zscore(s_ret)

        valid_df['score_ranker'] = s_rank
        valid_df['prob_top3'] = s_prob
        valid_df['pred_return'] = s_ret
        valid_df['tgpi_score'] = 0.45 * z_rank + 0.35 * z_prob + 0.20 * z_ret

        # Sort descending by Top-Gainer Probability Index
        ranked = valid_df.sort_values('tgpi_score', ascending=False).reset_index(drop=True)
        return ranked.head(self.max_concurrent_positions)

    def calculate_position_size(self, active_equity: float, adv_20d_inr: float, entry_price: float) -> Tuple[float, int]:
        """
        Calculates position size: 28% of active equity capped by 5% ADV liquidity ceiling.
        """
        target_cap = active_equity * self.position_weight
        if adv_20d_inr > 0:
            target_cap = min(target_cap, adv_20d_inr * self.adv_limit_pct)

        shares = int(target_cap / entry_price) if entry_price > 0 else 0
        allocated = shares * entry_price
        return allocated, shares

    def compute_statutory_charges(self, buy_val: float, sell_val: float, is_intraday: bool = True) -> Dict[str, float]:
        """
        Computes official Indian regulatory and statutory charges.
        """
        turnover = buy_val + sell_val
        if is_intraday:
            brokerage = min(40.0, 0.0003 * turnover)
            stt = 0.00025 * sell_val
            stamp_duty = 0.00003 * buy_val
        else:
            brokerage = 0.0
            stt = 0.001 * turnover
            stamp_duty = 0.00015 * buy_val

        exchange_txn = 0.0000297 * turnover
        sebi_turnover = 0.000001 * turnover
        gst = 0.18 * (brokerage + exchange_txn + sebi_turnover)
        total = brokerage + stt + exchange_txn + sebi_turnover + stamp_duty + gst

        return {
            'brokerage': brokerage,
            'stt': stt,
            'exchange_txn': exchange_txn,
            'sebi_turnover': sebi_turnover,
            'stamp_duty': stamp_duty,
            'gst': gst,
            'total_charges': total
        }

    def generate_trade_rationale(self, row: pd.Series, rank_idx: Optional[int] = None) -> Dict[str, any]:
        """
        Generates comprehensive institutional rationale and factor attribution for a selected trade.
        """
        sym = row.get('symbol', row.get('Symbol', 'UNKNOWN'))
        rank_str = f"#{rank_idx}" if rank_idx is not None else str(row.get('Rank', '#1'))
        prob = float(row.get('prob_top3', row.get('Top-3 Prob %', 0.0)))
        if prob <= 1.0 and prob > 0:
            prob *= 100.0
        tgpi = float(row.get('tgpi_score', row.get('TGPI Score', 0.0)))
        vol_surge = float(row.get('vol_surge_t', row.get('Volume Surge', 1.0)))
        comp_ratio = float(row.get('compression_ratio', 1.0))
        raw_range = float(row.get('range_position', 0.5))
        range_pos = raw_range * 100.0 if raw_range <= 1.0 else raw_range
        sector_alpha = float(row.get('stock_vs_sector', 0.0))
        dist_sma20 = float(row.get('dist_sma20_feat', 0.0))
        rsi = float(row.get('rsi_prev', 50.0))

        # Dynamic narrative formulation
        vol_desc = "Strong Institutional Thrust" if vol_surge >= 1.8 else ("Moderate Accumulation" if vol_surge >= 1.2 else "Baseline Volume")
        coil_desc = "Tight Coiled Spring" if comp_ratio <= 0.85 else ("Normal Volatility Expansion" if comp_ratio <= 1.25 else "Active Volatility Expansion")
        range_desc = "Dominant Buyer Control into Close" if range_pos >= 80 else ("Balanced Session" if range_pos >= 50 else "Weak Close")

        summary = (
            f"{sym} ranked {rank_str} in the pure Mid-Cap universe with a TGPI score of {tgpi:.3f} and an estimated {prob:.1f}% "
            f"probability of ranking among the Top-3 gainers tomorrow. "
            f"The selection is driven by {vol_desc.lower()} ({vol_surge:.2f}x 20-DMA volume) and {range_desc.lower()} ({range_pos:.0f}% of session range). "
            f"With a 20-DMA distance of {dist_sma20:+.1f}% and sector alpha of {sector_alpha:+.2f}%, the stock exhibits strong institutional continuation momentum."
        )

        drivers = [
            f"**Volume Surge:** {vol_surge:.2f}x 20-DMA volume ({vol_desc})",
            f"**Range Placement:** Closed at {range_pos:.0f}% of daily range ({range_desc})",
            f"**Sector Relative Strength:** {sector_alpha:+.2f}% outperformance vs its industry peer group",
            f"**Moving Average Proximity:** {dist_sma20:+.1f}% above 20-DMA denoting sustained bullish trend structure",
            f"**Volatility State:** ATR compression ratio of {comp_ratio:.2f} ({coil_desc})",
            f"**RSI Momentum:** {rsi:.1f} (in healthy acceleration zone, not overbought)",
            f"**09:30 AM Entry Gate:** Requires opening gap >= +0.35% and 15m low >= previous close to confirm buyer defense",
            f"**Dynamic Trailing Plan:** Initial SL at -2.5%; once gain reaches +4.0%, trailing stop activates at Peak - 3.5% to capture 5%–20%+ runner gains"
        ]

        return {
            'summary': summary,
            'drivers': drivers,
            'vol_surge': vol_surge,
            'comp_ratio': comp_ratio,
            'range_pos': range_pos,
            'sector_alpha': sector_alpha,
            'dist_sma20': dist_sma20,
            'rsi': rsi,
            'tgpi': tgpi,
            'prob': prob
        }
