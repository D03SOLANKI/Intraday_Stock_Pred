"""
Optional LSTM sequence model, capturing temporal dependencies in the raw
price/volume path that flat tabular features can miss (e.g., a specific
multi-day accumulation pattern). OFF BY DEFAULT (config.ENABLE_SEQUENCE_MODEL)
because it needs substantially more clean, gap-free per-symbol history than
free data sources (bhavcopy/yfinance) comfortably provide across the full
NSE universe -- turn on once you have a few years of clean daily bars per
stock with minimal missing sessions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from torch import nn

from config.settings import RANDOM_STATE
from models.base import BasePredictor

torch.manual_seed(RANDOM_STATE)


class _LSTMNet(nn.Module):
    def __init__(self, n_features: int, hidden_size: int = 32, num_layers: int = 1):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden_size, num_layers, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        last_step = out[:, -1, :]
        return self.head(last_step).squeeze(-1)


class LSTMSequenceModel(BasePredictor):
    """
    Expects X to already be reshaped into sequences upstream: a 3D array
    (n_samples, sequence_length, n_features) built from a symbol's trailing
    N days of features, wrapped in a DataFrame-compatible container. See
    `build_sequences()` for the reshaping helper -- this must be called on
    each symbol's OWN chronological history to avoid mixing time steps
    across different stocks or, worse, across time gaps.
    """
    name = "lstm_sequence_model"

    def __init__(self, n_features: int, sequence_length: int = 20,
                 hidden_size: int = 32, epochs: int = 30, lr: float = 1e-3):
        self.sequence_length = sequence_length
        self.epochs = epochs
        self.net = _LSTMNet(n_features, hidden_size)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=lr)
        self.loss_fn = nn.MSELoss()

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LSTMSequenceModel":
        X_t = torch.tensor(X, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32)
        self.net.train()
        for _ in range(self.epochs):
            self.optimizer.zero_grad()
            pred = self.net(X_t)
            loss = self.loss_fn(pred, y_t)
            loss.backward()
            self.optimizer.step()
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        self.net.eval()
        with torch.no_grad():
            X_t = torch.tensor(X, dtype=torch.float32)
            return self.net(X_t).numpy()


def build_sequences(
    symbol_feature_df: pd.DataFrame, feature_cols: list[str], sequence_length: int = 20
) -> tuple[np.ndarray, np.ndarray, pd.Series]:
    """
    Reshape one symbol's chronologically sorted feature history into
    overlapping sequences of length `sequence_length`, each paired with
    the label at the END of the sequence (so sequence [t-19..t] predicts
    label at t, which itself is the forward return from t to t+1 -- no
    future leakage since the label was already computed as a forward
    return in labels.py).
    """
    df = symbol_feature_df.sort_values("date").reset_index(drop=True)
    feats = df[feature_cols].fillna(0).to_numpy()
    labels = df["label_fwd_return"].to_numpy()
    dates = df["date"]

    X, y, out_dates = [], [], []
    for i in range(sequence_length, len(df)):
        if np.isnan(labels[i]):
            continue
        X.append(feats[i - sequence_length:i])
        y.append(labels[i])
        out_dates.append(dates.iloc[i])

    return np.array(X), np.array(y), pd.Series(out_dates)
