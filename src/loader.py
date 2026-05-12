"""
src/loader.py
─────────────
Reads bank statement Excel files and returns a cleaned, normalised DataFrame.
"""

import logging
import sys
from pathlib import Path

import pandas as pd

from utils.constants import (
    DESCRIPTION_COLUMN_CANDIDATES,
    INTERNAL_COLS,
)
from utils.helpers import detect_description_column, normalize_columns

logger = logging.getLogger(__name__)

_MAX_HEADER_SCAN_ROWS = 30

# Tokens used to score candidate header rows
_HEADER_TOKENS = {
    "particulars", "narration", "description", "remarks",
    "transaction details", "details", "transaction narration", "reference",
    "date", "transaction date", "value date",
    "debit", "credit", "balance",
    "cheque no", "cheque no.", "chq no", "ref no",
    "withdrawal", "deposit", "amount",
}


def load_excel(file_path: str | Path) -> pd.DataFrame:
    """
    Load a bank statement Excel file and return a cleaned, column-normalised DataFrame.

    Adds internal alias columns (_description, _debit, _credit, _date) used by the scorer.
    Original columns are preserved in full for export.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.error("Input file not found: %s", file_path)
        sys.exit(f"[ERROR] File not found: {file_path}")

    logger.info("Loading file: %s", file_path)
    header_row = _detect_header_row(file_path)
    logger.info("Detected header at row index: %d", header_row)

    try:
        df = pd.read_excel(file_path, header=header_row, engine="openpyxl")
    except Exception as exc:
        logger.error("Failed to read Excel: %s", exc)
        sys.exit(f"[ERROR] Cannot read {file_path}: {exc}")

    # Clean column names
    df.columns = df.columns.astype(str).str.strip()

    # Drop fully-empty rows and unnamed columns (artefacts above data)
    df.dropna(how="all", inplace=True)
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
    df.reset_index(drop=True, inplace=True)

    # ── Column normalisation (Fix #1) ─────────────────────────────────────────
    df = normalize_columns(df)

    desc_col = detect_description_column(df, DESCRIPTION_COLUMN_CANDIDATES)
    if desc_col is None:
        logger.warning(
            "No recognisable description column found. "
            "All transactions will be interpreted with low textual context. Columns: %s", list(df.columns),
        )
    else:
        logger.info("Using '%s' as the description column.", desc_col)

    logger.info("Loaded %d rows, %d columns.", len(df), len(df.columns) - len(INTERNAL_COLS))
    return df


def _detect_header_row(file_path: Path) -> int:
    """
    Score each of the first _MAX_HEADER_SCAN_ROWS rows and return the index
    of the row best matching known financial column keywords.
    """
    try:
        probe = pd.read_excel(file_path, header=None,
                              nrows=_MAX_HEADER_SCAN_ROWS, engine="openpyxl")
    except Exception:
        return 0

    best_row, best_score = 0, 0

    for row_idx, row in probe.iterrows():
        row_values = {str(v).lower().strip() for v in row if pd.notna(v)}
        score = len(row_values & _HEADER_TOKENS)
        if score > best_score:
            best_score = score
            best_row   = int(row_idx)  # type: ignore[arg-type]

    if best_score == 0:
        logger.debug("No header row detected by scoring; defaulting to row 0.")

    return best_row
