"""
Central configuration. Every tunable value in the system lives here, not
scattered as magic numbers inside logic files. Nothing here is a "trading
rule" — these are pipeline mechanics (windows, paths, validation splits).
Any value that looks like a trading threshold (e.g., "what counts as
unusual volume") is deliberately NOT hardcoded as a fixed number anywhere
in the codebase -- see features/volume_features.py, which computes such
things as statistical (z-score/percentile) measures learned from each
stock's own rolling distribution, not fixed cutoffs.
"""

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data_store"
RAW_DIR = DATA_DIR / "raw"
BHAVCOPY_DIR = RAW_DIR / "bhavcopy"
YFINANCE_DIR = RAW_DIR / "yfinance"
UNIVERSE_DIR = DATA_DIR / "universe"
FEATURE_STORE_DIR = DATA_DIR / "features"
MODEL_STORE_DIR = DATA_DIR / "models"
PREDICTION_LOG_DIR = DATA_DIR / "predictions"
EVAL_DIR = DATA_DIR / "evaluation"

for _d in [
    RAW_DIR, BHAVCOPY_DIR, YFINANCE_DIR, UNIVERSE_DIR,
    FEATURE_STORE_DIR, MODEL_STORE_DIR, PREDICTION_LOG_DIR, EVAL_DIR,
]:
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Market segments
# ---------------------------------------------------------------------------
SEGMENTS = ("large_cap", "mid_cap", "small_cap")

# Reference indices used to derive point-in-time segment membership.
# NOTE: free constituent history is limited -- see data/universe.py for the
# documented gap and how to slot in a paid source later.
SEGMENT_INDEX_MAP = {
    "large_cap": "NIFTY 100",
    "mid_cap": "NIFTY MIDCAP 150",
    "small_cap": "NIFTY SMALLCAP 250",
}

# ---------------------------------------------------------------------------
# Feature engineering windows (days)
# ---------------------------------------------------------------------------
RETURN_WINDOWS = (1, 3, 5, 10, 20)
MOVING_AVG_WINDOWS = (20, 50, 200)
VOLATILITY_WINDOWS = (10, 20)
VOLUME_ZSCORE_WINDOW = 20
RSI_WINDOW = 14
ATR_WINDOW = 14
BOLLINGER_WINDOW = 20
BOLLINGER_STD = 2
PIVOT_LOOKBACK = 20
BETA_WINDOW = 60

# ---------------------------------------------------------------------------
# Labeling
# ---------------------------------------------------------------------------
LABEL_HORIZON_DAYS = 1  # predict next-session return
LABEL_PRICE_FIELD = "close"  # "close" -> close-to-close; "open" for open-to-close variant
TOP_DECILE_THRESHOLD = 0.90  # for the classification-style "is top gainer" target,
                              # this is a *percentile* within each day's cross-section,
                              # not a fixed % return cutoff -- so it adapts to regime.

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
WALK_FORWARD_TRAIN_MIN_DAYS = 504     # ~2 trading years minimum initial train window
WALK_FORWARD_TEST_DAYS = 63           # ~1 trading quarter test block
WALK_FORWARD_STEP_DAYS = 63           # roll forward by one quarter each iteration
PURGE_EMBARGO_DAYS = 5                # embargo around train/test boundary to prevent
                                       # leakage via overlapping rolling-window features
FINAL_HOLDOUT_DAYS = 252              # last ~1 year never touched until final eval

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
RANDOM_STATE = 42
ENABLE_SEQUENCE_MODEL = False  # LSTM needs more data volume than free sources
                                # typically provide cleanly; off by default.
N_ENSEMBLE_TOP_FEATURES_TO_EXPLAIN = 6

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
TOP_N_PER_SEGMENT = 3
