"""
src/scorer.py
─────────────
Multi-signal scoring engine for transaction classification. (Phase 2)

Each transaction is scored independently for TDS and GST using:
  • Keyword signals          (Fix #1 whole-word, Fix #12 no bare "tax")
  • Transaction-type signals (Fix #5)
  • Debit/credit direction   (Fix #2)
  • Amount sanity            (Fix #3)
  • Priority override        (Fix #4)
  • Soft negative penalties  (Fix #6)
  • Config-driven weights    (Fix #9)
  • Precompiled regex        (Fix #10)
  • UNCERTAIN fallback       (Fix #11)
  • Decision logging         (Fix #8)
"""

import logging
import re
from dataclasses import dataclass, field

import pandas as pd

from src.parser import TxType, parse_transaction_type
from utils.constants import (
    AMOUNT_FLAG_ABOVE, AMOUNT_IGNORE_BELOW,
    CATEGORY_GST, CATEGORY_NORMAL, CATEGORY_TDS, CATEGORY_UNCERTAIN,
    GST_KEYWORDS, MERCHANT_KEYWORDS, NEGATIVE_KEYWORDS,
    INTERNAL_CREDIT_COL, INTERNAL_DATE_COL,
    INTERNAL_DEBIT_COL, INTERNAL_DESCRIPTION_COL,
    PENALTY_INCOMING_GST, PENALTY_INCOMING_TDS,
    SCORE_CLOSE_CALL_MARGIN, SCORE_GST_CMS_CARDPMT, SCORE_GST_GATEWAY,
    SCORE_GST_GSTIN_PATTERN, SCORE_GST_KEYWORD, SCORE_GST_NONROUND_AMT,
    SCORE_HIGH_THRESHOLD, SCORE_MEDIUM_THRESHOLD,
    SCORE_TDS_KEYWORD, SCORE_TDS_QUARTER_END,
    SCORE_TDS_SECTION_CODE, SCORE_TDS_TXTYPE_BLKNEFT,
    SCORE_UNCERTAIN_CUTOFF, TDS_KEYWORDS, TDS_SECTION_CODES,
)
from utils.helpers import normalize_text

logger = logging.getLogger(__name__)

# ── Precompiled regex patterns (Fix #10) ──────────────────────────────────────

# TDS keywords — whole-word boundaries
_RE_TDS_KEYWORDS: list[tuple[str, re.Pattern]] = [
    (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
    for kw in TDS_KEYWORDS
]

# Section codes matched with letter suffix (194A, 194J …)
_RE_SECTION_WITH_LETTER: list[re.Pattern] = [
    re.compile(rf"\b{code}[A-Z]\b", re.IGNORECASE)
    for code in TDS_SECTION_CODES
]
# Section codes matched when preceded by "tds" or "section"
_RE_SECTION_CONTEXT = re.compile(
    r"(tds|section)\s*(" + "|".join(TDS_SECTION_CODES) + r")\b",
    re.IGNORECASE,
)

# GST keywords — whole-word boundaries
_RE_GST_KEYWORDS: list[tuple[str, re.Pattern]] = [
    (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
    for kw in GST_KEYWORDS
]

# GSTIN: 2-digit state + 5-alpha PAN prefix + 4-digit + alpha + Z + alphanumeric
_RE_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][Z][A-Z0-9]\b")

# Merchant keywords — simple substring (names don't need word boundaries)
# Pre-built as set for O(1) lookup
_MERCHANT_SET = set(MERCHANT_KEYWORDS)

# Negative keyword patterns (Fix #6 — soft penalties, not cancellations)
_NEGATIVE_PATTERNS: list[tuple[re.Pattern, int]] = [
    (
        re.compile(pattern if is_regex else re.escape(pattern), re.IGNORECASE),
        penalty,
    )
    for pattern, is_regex, penalty in NEGATIVE_KEYWORDS
]

# Quarter-end months for TDS date signal
_QUARTER_END_MONTHS = {3, 6, 9, 12}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ScoreResult:
    tds_score:    int  = 0
    gst_score:    int  = 0
    category:     str  = CATEGORY_NORMAL
    confidence:   str  = "HIGH"
    needs_review: bool = False
    debug_parts:  list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "Category":     self.category,
            "Confidence":   self.confidence,
            "Needs_Review": self.needs_review,
        }


# ── Main scoring function ─────────────────────────────────────────────────────

def score_transaction(row: pd.Series) -> ScoreResult:
    """
    Score a single transaction row and return a ScoreResult.
    Reads internal alias columns (_description, _debit, _credit, _date).
    """
    result = ScoreResult()
    dbg    = result.debug_parts

    # ── Extract values ────────────────────────────────────────────────────────
    text   = normalize_text(row.get(INTERNAL_DESCRIPTION_COL, ""))
    debit  = _safe_float(row.get(INTERNAL_DEBIT_COL))
    credit = _safe_float(row.get(INTERNAL_CREDIT_COL))
    date   = row.get(INTERNAL_DATE_COL)
    amount = debit if debit > 0 else credit

    # ── Amount sanity (Fix #3) ────────────────────────────────────────────────
    if 0 < amount < AMOUNT_IGNORE_BELOW:
        dbg.append(f"amount ₹{amount} < ₹1 → NORMAL (skip scoring)")
        return _finalise(result, debit, credit, amount, dbg)

    # ── Transaction type (Fix #5) ─────────────────────────────────────────────
    tx_type = parse_transaction_type(text)
    dbg.append(f"tx={tx_type.value}")

    # ATM → always NORMAL, short-circuit
    if tx_type == TxType.ATM_WITHDRAWAL:
        dbg.append("ATM withdrawal → NORMAL override")
        return _finalise(result, debit, credit, amount, dbg)

    # ── Negative penalties (Fix #6 — soft, not cancel) ───────────────────────
    neg = _negative_penalty(text, dbg)

    # ── TDS scoring ───────────────────────────────────────────────────────────
    tds = 0

    for kw, pattern in _RE_TDS_KEYWORDS:
        if pattern.search(text):
            tds += SCORE_TDS_KEYWORD
            dbg.append(f"TDS kw '{kw}' +{SCORE_TDS_KEYWORD}")
            break  # count once

    for pattern in _RE_SECTION_WITH_LETTER:
        if pattern.search(text):
            tds += SCORE_TDS_SECTION_CODE
            dbg.append(f"TDS section code (letter) +{SCORE_TDS_SECTION_CODE}")
            break
    else:
        if _RE_SECTION_CONTEXT.search(text):
            tds += SCORE_TDS_SECTION_CODE
            dbg.append(f"TDS section code (context) +{SCORE_TDS_SECTION_CODE}")

    if tx_type == TxType.BULK_NEFT:
        tds += SCORE_TDS_TXTYPE_BLKNEFT
        dbg.append(f"TDS BLKNEFT +{SCORE_TDS_TXTYPE_BLKNEFT}")

    if _is_quarter_end(date):
        tds += SCORE_TDS_QUARTER_END
        dbg.append(f"TDS quarter-end +{SCORE_TDS_QUARTER_END}")

    # ── GST scoring ───────────────────────────────────────────────────────────
    gst = 0

    if _RE_GSTIN.search(text.upper()):
        gst += SCORE_GST_GSTIN_PATTERN
        dbg.append(f"GST GSTIN +{SCORE_GST_GSTIN_PATTERN}")

    for kw, pattern in _RE_GST_KEYWORDS:
        if pattern.search(text):
            gst += SCORE_GST_KEYWORD
            dbg.append(f"GST kw '{kw}' +{SCORE_GST_KEYWORD}")
            break

    for kw in _MERCHANT_SET:
        if kw in text:
            gst += SCORE_GST_GATEWAY
            dbg.append(f"GST merchant '{kw}' +{SCORE_GST_GATEWAY}")
            break

    if tx_type in (TxType.CMS, TxType.CARD_PAYMENT):
        gst += SCORE_GST_CMS_CARDPMT
        dbg.append(f"GST CMS/card +{SCORE_GST_CMS_CARDPMT}")

    if debit > 0 and _is_nonround(debit):
        gst += SCORE_GST_NONROUND_AMT
        dbg.append(f"GST non-round amt +{SCORE_GST_NONROUND_AMT}")

    # ── Apply soft negative penalties to both (Fix #6) ───────────────────────
    tds = max(0, tds + neg)
    gst = max(0, gst + neg)

    # ── Direction penalty — incoming credits (Fix #2) ─────────────────────────
    is_incoming = (credit > 0 and debit == 0)
    if is_incoming:
        tds = max(0, tds + PENALTY_INCOMING_TDS)
        gst = max(0, gst + PENALTY_INCOMING_GST)
        dbg.append(f"incoming: TDS{PENALTY_INCOMING_TDS} GST{PENALTY_INCOMING_GST}")

    result.tds_score = tds
    result.gst_score = gst

    # ── Category decision (Fix #4 — priority override) ───────────────────────
    if tds >= SCORE_HIGH_THRESHOLD:
        # Strong TDS always wins — even if GST signals also present
        result.category = CATEGORY_TDS
        dbg.append(f"TDS priority override tds={tds} ≥ {SCORE_HIGH_THRESHOLD}")

    elif gst >= SCORE_HIGH_THRESHOLD:
        result.category = CATEGORY_GST
        dbg.append(f"GST high tds={tds} gst={gst}")

    elif tds >= SCORE_MEDIUM_THRESHOLD and tds >= gst:
        result.category = CATEGORY_TDS
        dbg.append(f"TDS medium tds={tds}")

    elif gst >= SCORE_MEDIUM_THRESHOLD:
        result.category = CATEGORY_GST
        dbg.append(f"GST medium gst={gst}")

    elif max(tds, gst) < SCORE_UNCERTAIN_CUTOFF:
        result.category = CATEGORY_UNCERTAIN  # Fix #11
        dbg.append(f"UNCERTAIN — both below cutoff {SCORE_UNCERTAIN_CUTOFF}")

    else:
        result.category = CATEGORY_NORMAL

    return _finalise(result, debit, credit, amount, dbg)


# ── Finalise confidence + Needs_Review ────────────────────────────────────────

def _finalise(result: ScoreResult, debit: float, credit: float,
              amount: float, dbg: list) -> ScoreResult:
    tds, gst = result.tds_score, result.gst_score
    top = max(tds, gst)

    # Confidence
    if top >= SCORE_HIGH_THRESHOLD:
        result.confidence = "HIGH"
    elif top >= SCORE_MEDIUM_THRESHOLD:
        result.confidence = "MEDIUM"
    else:
        result.confidence = "LOW"

    # Needs_Review (Fix #7)
    close_call = (abs(tds - gst) <= SCORE_CLOSE_CALL_MARGIN and top > 0)
    result.needs_review = (
        result.confidence == "LOW"
        or result.category == CATEGORY_UNCERTAIN
        or close_call
        or (amount > AMOUNT_FLAG_ABOVE and top < SCORE_HIGH_THRESHOLD)
    )

    # Decision log (Fix #8)
    logger.debug(
        "[%s|%s|review=%s] tds=%d gst=%d | %s",
        result.category, result.confidence, result.needs_review,
        tds, gst, " → ".join(dbg),
    )
    return result


# ── Private helpers ───────────────────────────────────────────────────────────

def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _is_nonround(amount: float) -> bool:
    return int(amount * 100) % 100 not in (0, 50)


def _is_quarter_end(date_val) -> bool:
    if date_val is None or (isinstance(date_val, float) and pd.isna(date_val)):
        return False
    try:
        if hasattr(date_val, "month"):
            return date_val.month in _QUARTER_END_MONTHS
        parsed = pd.to_datetime(date_val, dayfirst=True, errors="coerce")
        return pd.notna(parsed) and parsed.month in _QUARTER_END_MONTHS
    except Exception:
        return False


def _negative_penalty(text: str, dbg: list) -> int:
    total = 0
    for pattern, penalty in _NEGATIVE_PATTERNS:
        if pattern.search(text):
            total += penalty
            dbg.append(f"neg '{pattern.pattern}' {penalty}")
    return total
