import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import pandas as pd
import numpy as np
import lightgbm as lgb

print("=" * 80)
print("TRAINING AND SERIALIZING PRODUCTION TOP-3 ML MODELS")
print("=" * 80)

# Load engineered features
df = pd.read_pickle('ml/engineered_features_dataset.pkl')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(['date', 'symbol']).reset_index(drop=True)

feature_cols = [
    'ret_1d', 'ret_3d', 'ret_5d', 'ret_10d', 'ret_20d',
    'dist_sma20_feat', 'dist_sma50_feat', 'sma20_trend',
    'true_range_pct', 'atr_5d', 'atr_20d', 'compression_ratio',
    'vol_surge_t', 'vol_accel_feat', 'adv_20d_cr',
    'range_position', 'stock_vs_sector',
    'dist_52w_high', 'rsi_prev'
]

# We train on historical baseline up to 2024-12-31 to evaluate cleanly on 2025-2026 holdout,
# or train across full dataset for live deployment
SPLIT_DATE = '2025-01-01'
train_df = df[df['date'] < SPLIT_DATE].copy()

train_groups = train_df.groupby('date').size().values
X_train = train_df[feature_cols]
y_train_return = train_df['target_next_day_return']
y_train_top3 = train_df['target_is_top3']
y_train_rel = train_df['target_relevance']

print(f"Training on {len(train_df):,} samples across {train_df['date'].nunique()} sessions...")

# 1. LambdaMART Ranker
print("Training LambdaMART Ranker...")
ranker = lgb.LGBMRanker(
    objective='lambdarank',
    metric='ndcg',
    eval_at=[1, 3, 5],
    n_estimators=150,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    importance_type='gain'
)
ranker.fit(X_train, y_train_rel, group=train_groups)
ranker.booster_.save_model('ml/models/ranker.txt')
print("Saved ml/models/ranker.txt")

# 2. Top-3 Probability Classifier
print("Training Probability Classifier...")
pos_weight = (len(y_train_top3) - y_train_top3.sum()) / y_train_top3.sum()
classifier = lgb.LGBMClassifier(
    objective='binary',
    n_estimators=150,
    learning_rate=0.03,
    num_leaves=31,
    scale_pos_weight=pos_weight,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    importance_type='gain'
)
classifier.fit(X_train, y_train_top3)
classifier.booster_.save_model('ml/models/classifier.txt')
print("Saved ml/models/classifier.txt")

# 3. Expected Return Regressor
print("Training Expected Return Regressor...")
regressor = lgb.LGBMRegressor(
    objective='huber',
    n_estimators=150,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=50,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    importance_type='gain'
)
regressor.fit(X_train, y_train_return)
regressor.booster_.save_model('ml/models/regressor.txt')
print("Saved ml/models/regressor.txt")

# Save feature metadata
with open('ml/models/feature_metadata.json', 'w') as f:
    json.dump({
        'features': feature_cols,
        'train_cutoff': SPLIT_DATE,
        'total_train_samples': len(train_df),
        'total_train_dates': int(train_df['date'].nunique())
    }, f, indent=2)

print("Saved ml/models/feature_metadata.json")
print("All production models successfully trained and serialized.")
