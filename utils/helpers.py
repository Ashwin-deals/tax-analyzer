"""
utils/helpers.py
────────────────
Shared utility functions used across all modules.
"""

import re
import logging
import pandas as pd

from utils.constants import (
    DESCRIPTION_COLUMN_CANDIDATES,
    DEBIT_COLUMN_CANDIDATES,
    CREDIT_COLUMN_CANDIDATES,
    DATE_COLUMN_CANDIDATES,
    INTERNAL_DESCRIPTION_COL,
    INTERNAL_DEBIT_COL,
    INTERNAL_CREDIT_COL,
    INTERNAL_DATE_COL,
    CATEGORY_TDS, CATEGORY_GST, CATEGORY_NORMAL, CATEGORY_UNCERTAIN,
)

logger = logging.getLogger(__name__)


# ── Text normalisation ────────────────────────────────────────────────────────

def normalize_text(text) -> str:
    """Lowercase, strip, collapse whitespace, and normalise abbreviation formats.

    Pre-processing steps (applied before keyword matching):
      - T.D.S  → tds       (dotted abbreviations)
      - G.S.T  → gst
      - TDSPMT → tds pmt   (camel/run-together → space-separated)
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    t = str(text).strip()
    # Fix #4a — Remove dots between single uppercase letters: T.D.S → TDS
    t = re.sub(r'\b([A-Za-z])\.((?:[A-Za-z]\.)+[A-Za-z])\b',
                lambda m: m.group(0).replace('.', ''), t)
    # Fix #4b — Insert space at letter→digit and digit→letter boundaries
    t = re.sub(r'([A-Za-z])(\d)', r'\1 \2', t)
    t = re.sub(r'(\d)([A-Za-z])', r'\1 \2', t)
    return re.sub(r'\s+', ' ', t.lower().strip())


# ── Column detection ──────────────────────────────────────────────────────────

def detect_description_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first matching column name (case-insensitive) or None."""
    lower_map = {c.lower().strip(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


# ── Column normalisation (Fix #1) ─────────────────────────────────────────────

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add internal alias columns (_description, _debit, _credit, _date) to df.

    Original columns are untouched. Internal columns are used only by the
    scorer/classifier and are dropped before export.

    Returns the modified DataFrame (operates on a copy).
    """
    df = df.copy()
    lower_map = {c.lower().strip(): c for c in df.columns}

    def _add_alias(candidates: list[str], alias: str) -> str | None:
        for candidate in candidates:
            if candidate.lower() in lower_map:
                original = lower_map[candidate.lower()]
                df[alias] = df[original]
                logger.debug("Mapped '%s' → '%s'", original, alias)
                return original
        df[alias] = None
        logger.debug("No column found for alias '%s'; set to None.", alias)
        return None

    found = {
        "description": _add_alias(DESCRIPTION_COLUMN_CANDIDATES, INTERNAL_DESCRIPTION_COL),
        "debit":       _add_alias(DEBIT_COLUMN_CANDIDATES,       INTERNAL_DEBIT_COL),
        "credit":      _add_alias(CREDIT_COLUMN_CANDIDATES,      INTERNAL_CREDIT_COL),
        "date":        _add_alias(DATE_COLUMN_CANDIDATES,        INTERNAL_DATE_COL),
    }

    logger.info(
        "Column mapping — description: %s | debit: %s | credit: %s | date: %s",
        found["description"], found["debit"], found["credit"], found["date"],
    )
    return df


# ── Numeric coercion ──────────────────────────────────────────────────────────

def safe_numeric(series: pd.Series) -> pd.Series:
    """Coerce column to numeric, replacing un-parseable values with 0."""
    return pd.to_numeric(series, errors="coerce").fillna(0)


# ── Summary builder ───────────────────────────────────────────────────────────

def build_summary(classified_df: pd.DataFrame) -> pd.DataFrame:
    """Build a per-category summary with counts, totals, and review flags."""
    rows = []
    order = {CATEGORY_TDS: 0, CATEGORY_GST: 1, CATEGORY_NORMAL: 2, CATEGORY_UNCERTAIN: 3}

    for category, group in classified_df.groupby("Category", sort=False):
        row: dict = {
            "Category":           category,
            "Transaction Count":  len(group),
            "Needs Review Count": int(group.get("Needs_Review", pd.Series([False] * len(group))).sum()),
        }
        for col in ["Debit", "Credit", "Amount", "Withdrawal Amt.", "Deposit Amt."]:
            matched = [c for c in group.columns if c.strip().lower() == col.strip().lower()]
            if matched:
                row[f"Total {matched[0]}"] = safe_numeric(group[matched[0]]).sum()
        rows.append(row)

    summary_df = pd.DataFrame(rows)
    summary_df["_order"] = summary_df["Category"].map(order).fillna(99)
    summary_df = summary_df.sort_values("_order").drop(columns=["_order"])
    return summary_df.reset_index(drop=True)