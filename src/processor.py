"""
src/processor.py
────────────────
Orchestrates scoring + transformation after loading.

Applies the multi-signal scorer to every row, adds Category / Confidence /
Needs_Review columns, drops internal alias columns before export, and
splits into per-category DataFrames including UNCERTAIN.
"""

import logging

import pandas as pd

from src.scorer import score_transaction
from utils.constants import (
    CATEGORY_GST, CATEGORY_NORMAL, CATEGORY_TDS, CATEGORY_UNCERTAIN, CATEGORY_POSSIBLE_GST,
    INTERNAL_COLS,
)

logger = logging.getLogger(__name__)


def process_transactions(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Score and classify all transactions. Returns a dict keyed by category.

    Keys: 'GST', 'TDS', 'NORMAL', 'UNCERTAIN'
    Each value is a DataFrame with original columns + Category, Confidence,
    Needs_Review. Internal alias columns (_description etc.) are dropped.
    """
    if df.empty:
        logger.warning("Input DataFrame is empty — nothing to process.")
        empty = pd.DataFrame()
        return {k: empty for k in [CATEGORY_GST, CATEGORY_TDS, CATEGORY_NORMAL, CATEGORY_UNCERTAIN]}

    logger.info("Scoring %d transactions …", len(df))

    # ── Apply scorer row by row ───────────────────────────────────────────────
    score_results = df.apply(score_transaction, axis=1)

    df = df.copy()
    df["Category"]            = [r.category            for r in score_results]
    df["Confidence"]          = [r.confidence          for r in score_results]
    df["Classification_Mode"] = [r.classification_mode for r in score_results]
    df["Needs_Review"]        = [r.needs_review        for r in score_results]
    df["Reason"]              = [r.reason              for r in score_results]

    # ── Drop internal alias columns before export ──────────────────────────────
    cols_to_drop = [c for c in INTERNAL_COLS if c in df.columns]
    df.drop(columns=cols_to_drop, inplace=True)

    # ── Log breakdown ─────────────────────────────────────────────────────────
    counts = df["Category"].value_counts().to_dict()
    review_count = int(df["Needs_Review"].sum())
    logger.info("Classification: %s | Needs review: %d", counts, review_count)

    # ── Split ─────────────────────────────────────────────────────────────────
    result = {
        CATEGORY_GST:          _filter(df, CATEGORY_GST),
        CATEGORY_POSSIBLE_GST: _filter(df, CATEGORY_POSSIBLE_GST),
        CATEGORY_TDS:          _filter(df, CATEGORY_TDS),
        CATEGORY_NORMAL:       _filter(df, CATEGORY_NORMAL),
        CATEGORY_UNCERTAIN:    _filter(df, CATEGORY_UNCERTAIN),
    }

    logger.info(
        "Split — GST: %d, POSSIBLE_GST: %d, TDS: %d, NORMAL: %d, UNCERTAIN: %d",
        len(result[CATEGORY_GST]), len(result[CATEGORY_POSSIBLE_GST]), len(result[CATEGORY_TDS]),
        len(result[CATEGORY_NORMAL]), len(result[CATEGORY_UNCERTAIN]),
    )
    return result


def _filter(df: pd.DataFrame, category: str) -> pd.DataFrame:
    return df[df["Category"] == category].reset_index(drop=True)