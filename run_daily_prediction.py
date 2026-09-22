#!/usr/bin/env python3
"""
Daily entrypoint. In production, schedule this to run after market close
(so bhavcopy for today is available) and before the next session opens.

Usage:
    python run_daily_prediction.py

This scaffold prints guidance rather than running end-to-end against live
data, since that requires your symbol universe / trained models to already
exist (see README.md "Next steps"). Once pipeline/train_pipeline.py has
been run and models are persisted in data_store/models/, wire the actual
data pull + feature computation here and call
pipeline.inference_pipeline.run_daily_inference(...).
"""

from datetime import date

from config.settings import MODEL_STORE_DIR


def main():
    trained_models_exist = any(MODEL_STORE_DIR.glob("ensemble_*.pkl"))
    if not trained_models_exist:
        print(
            "No trained models found in data_store/models/.\n"
            "Run the training pipeline first:\n"
            "  python -m pipeline.train_pipeline --stage data\n"
            "  python -m pipeline.train_pipeline --stage train\n"
            "  python -m pipeline.train_pipeline --stage final_holdout\n"
        )
        return

    print(
        f"[{date.today().isoformat()}] Trained models found. Wire up "
        "today's data pull + feature computation here, then call "
        "pipeline.inference_pipeline.run_daily_inference(...). "
        "See pipeline/inference_pipeline.py for the expected inputs."
    )


if __name__ == "__main__":
    main()
