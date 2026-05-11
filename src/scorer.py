"""
src/scorer.py
─────────────
Multi-signal scoring engine for transaction classification.

Architecture (v3):
  1. NORMAL_OVERRIDE_KEYWORDS  — hard utility/statutory bypass before scoring
  2. Vendor override CSV       — loaded once at startup; HARD/SOFT precedence
  3. Salary credit override    — hard override for incoming salary credits
  4. ATM override              — always NORMAL
  5. TDS scoring               — keywords, section codes, BLKNEFT, quarter-end
  6. GST scoring               — keywords, GSTIN, merchant, CMS/card, UPI, non-round
  7. Negative penalties        — soft subtraction from both scores
  8. Company suffix penalties  — TDS-only subtraction
  9. Direction penalty         — incoming credits penalised
 10. Category decision         — HIGH > MEDIUM > SOFT GST > UNCERTAIN > NORMAL
     UNCERTAIN only fires when BOTH scores ≥ SCORE_UNCERTAIN_CUTOFF
 11. Reason string             — human-readable explanation in every result
"""

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.parser import TxType, parse_transaction_type
from utils.constants import (
    AMOUNT_FLAG_ABOVE, AMOUNT_IGNORE_BELOW,
    CATEGORY_GST, CATEGORY_NORMAL, CATEGORY_TDS, CATEGORY_UNCERTAIN, CATEGORY_POSSIBLE_GST,
    COMPANY_SUFFIX_PENALTIES,
    GST_KEYWORDS, MERCHANT_KEYWORDS, NEGATIVE_KEYWORDS,
    NORMAL_OVERRIDE_KEYWORDS,
    INTERNAL_CREDIT_COL, INTERNAL_DATE_COL,
    INTERNAL_DEBIT_COL, INTERNAL_DESCRIPTION_COL,
    PENALTY_INCOMING_GST, PENALTY_INCOMING_TDS,
    SCORE_CLOSE_CALL_MARGIN, SCORE_GST_CMS_CARDPMT, SCORE_GST_GATEWAY,
    SCORE_GST_GSTIN_PATTERN, SCORE_GST_KEYWORD, SCORE_GST_NONROUND_AMT,
    SCORE_GST_UPI_DEBIT,
    SCORE_HIGH_THRESHOLD, SCORE_MEDIUM_THRESHOLD,
    SCORE_TDS_KEYWORD, SCORE_TDS_QUARTER_END,
    SCORE_TDS_SECTION_CODE, SCORE_TDS_TXTYPE_BLKNEFT,
    SCORE_UNCERTAIN_CUTOFF, TDS_KEYWORDS, TDS_SECTION_CODES,
)
from utils.helpers import normalize_text

logger = logging.getLogger(__name__)

# ── Precompiled regex patterns ────────────────────────────────────────────────

_RE_TDS_KEYWORDS: list[tuple[str, re.Pattern]] = [
    (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
    for kw in TDS_KEYWORDS
]

_RE_SECTION_WITH_LETTER: list[re.Pattern] = [
    re.compile(rf"\b{code}[A-Z]{{1,3}}\b", re.IGNORECASE)
    for code in TDS_SECTION_CODES
]
_RE_SECTION_CONTEXT = re.compile(
    r"(tds|section)\s*(" + "|".join(TDS_SECTION_CODES) + r")\b",
    re.IGNORECASE,
)

_RE_GST_KEYWORDS: list[tuple[str, re.Pattern]] = [
    (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
    for kw in GST_KEYWORDS
]

_RE_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][Z][A-Z0-9]\b")

_MERCHANT_SET = set(MERCHANT_KEYWORDS)

_NEGATIVE_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(p if is_re else re.escape(p), re.IGNORECASE), pen)
    for p, is_re, pen in NEGATIVE_KEYWORDS
]

_COMPANY_SUFFIX_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(p if is_re else re.escape(p), re.IGNORECASE), pen)
    for p, is_re, pen in COMPANY_SUFFIX_PENALTIES
]

# NORMAL override patterns — utility boards, statutory payments
_NORMAL_OVERRIDE_PATTERNS: list[re.Pattern] = [
    re.compile(p if is_re else re.escape(p), re.IGNORECASE)
    for p, is_re in NORMAL_OVERRIDE_KEYWORDS
]

# Strong GST keywords that block TDS priority and (when present) bypass
# NORMAL overrides (e.g. "TNEB GST PAYMENT" must stay GST, not become NORMAL)
_STRONG_GST_KWS = {"igst", "cgst", "sgst", "utgst", "gst payment",
                   "gst challan", "gst refund"}
# Strong TDS keywords that block NORMAL overrides
_STRONG_TDS_KWS = {"tds", "tax deducted", "income tax", "tcs", "it refund"}

_QUARTER_END_MONTHS = {3, 6, 9, 12}

# ── Vendor overrides — loaded once at module import ───────────────────────────
# Structure: list of (pattern_lower, category, priority)
# priority: "HARD" or "SOFT"
_VENDOR_OVERRIDES: list[tuple[str, str, str]] = []

def _load_vendor_overrides() -> list[tuple[str, str, str]]:
    csv_path = Path(__file__).resolve().parent.parent / "data" / "vendor_overrides.csv"
    overrides: list[tuple[str, str, str]] = []
    if not csv_path.exists():
        return overrides
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(
            (line for line in fh if not line.lstrip().startswith("#")),
        )
        for row in reader:
            pattern  = row.get("vendor_pattern", "").strip().lower()
            category = row.get("category", "").strip().upper()
            priority = row.get("priority", "SOFT").strip().upper()
            if pattern and category in (CATEGORY_GST, CATEGORY_TDS, CATEGORY_NORMAL):
                overrides.append((pattern, category, priority))
    logger.debug("Loaded %d vendor overrides from %s", len(overrides), csv_path)
    return overrides

_VENDOR_OVERRIDES = _load_vendor_overrides()


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ScoreResult:
    tds_score:    int  = 0
    gst_score:    int  = 0
    category:     str  = CATEGORY_NORMAL
    confidence:   str  = "HIGH"
    classification_mode: str = "HEURISTIC"
    needs_review: bool = False
    reason:       str  = ""          # ← human-readable explanation
    debug_parts:  list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "Category":     self.category,
            "Confidence":   self.confidence,
            "Mode":         self.classification_mode,
            "Needs_Review": self.needs_review,
            "Reason":       self.reason,
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

    # ── Amount sanity ─────────────────────────────────────────────────────────
    if 0 < amount < AMOUNT_IGNORE_BELOW:
        dbg.append(f"amount ₹{amount} < ₹{AMOUNT_IGNORE_BELOW} → skip scoring")
        return _finalise(result, debit, credit, amount, dbg)

    # ── Probe for strong tax keywords (used by override bypass logic) ─────────
    has_strong_gst = any(kw in text for kw in _STRONG_GST_KWS)
    has_strong_tds = any(kw in text for kw in _STRONG_TDS_KWS)
    
    result.classification_mode = "EXPLICIT" if (has_strong_gst or has_strong_tds) else "HEURISTIC"

    # ── NORMAL override: utility / statutory payments ─────────────────────────
    # If a utility keyword matches AND no strong GST/TDS keyword is present,
    # immediately return NORMAL. This replaces fragile large negative penalties.
    if not has_strong_gst and not has_strong_tds:
        for pat in _NORMAL_OVERRIDE_PATTERNS:
            if pat.search(text):
                dbg.append(f"Statutory/utility payment detected")
                result.category = CATEGORY_NORMAL
                return _finalise(result, debit, credit, amount, dbg)

    # ── Salary credit hard override ───────────────────────────────────────────
    _SALARY_SIGNALS = ("salary", "net salary", "payroll", "wages")
    if credit > 0 and debit == 0 and any(s in text for s in _SALARY_SIGNALS):
        dbg.append("Salary credit detected")
        result.category = CATEGORY_NORMAL
        return _finalise(result, debit, credit, amount, dbg)

    # ── Transaction type ──────────────────────────────────────────────────────
    tx_type = parse_transaction_type(text)

    if tx_type == TxType.ATM_WITHDRAWAL:
        dbg.append("ATM withdrawal detected")
        return _finalise(result, debit, credit, amount, dbg)

    # ── Vendor override (CSV-driven) ──────────────────────────────────────────
    # Applied after ATM/salary hard overrides but BEFORE scoring.
    # HARD: forces category unless a strong opposing tax keyword blocks it.
    # SOFT: applies only when no strong GST/TDS signal detected.
    vendor_override_cat   = None
    vendor_override_prio  = None
    for pattern, category, priority in _VENDOR_OVERRIDES:
        if pattern in text:
            vendor_override_cat  = category
            vendor_override_prio = priority
            dbg.append(f"vendor override '{pattern}' → {category} ({priority})")
            break

    if vendor_override_cat == CATEGORY_NORMAL:
        if vendor_override_prio == "HARD" and not has_strong_gst and not has_strong_tds:
            result.category = CATEGORY_NORMAL
            dbg.append("Known non-tax vendor matched")
            return _finalise(result, debit, credit, amount, dbg)
        # SOFT: deferred — applied at end of decision tree if no strong signal

    # ── TDS scoring ───────────────────────────────────────────────────────────
    tds = 0

    for kw, pattern in _RE_TDS_KEYWORDS:
        if pattern.search(text):
            tds += SCORE_TDS_KEYWORD
            result.classification_mode = "EXPLICIT"
            dbg.append("Explicit TDS keyword found")
            break  # count once

    for pattern in _RE_SECTION_WITH_LETTER:
        match = pattern.search(text)
        if match:
            matched_code = match.group(0).upper()
            result.classification_mode = "EXPLICIT"
            if "194A" in matched_code:
                tds += 6
                dbg.append("TDS section 194A detected")
            elif "194J" in matched_code:
                tds += 8
                dbg.append("TDS section 194J detected")
            else:
                tds += 8
                dbg.append(f"TDS section {matched_code} detected")
            break
    else:
        if _RE_SECTION_CONTEXT.search(text):
            tds += SCORE_TDS_SECTION_CODE
            result.classification_mode = "EXPLICIT"
            dbg.append("Contextual TDS section code detected")

    # Bare section code (194/195/206) — no debit condition required anymore
    if tds == 0:
        if re.search(r'\b(192|193|194|195|196|206)\b', text):
            tds += 4
            dbg.append("Implicit TDS section code detected")

    if tx_type == TxType.BULK_NEFT:
        tds += SCORE_TDS_TXTYPE_BLKNEFT
        dbg.append("Bulk NEFT format detected")

    if _is_quarter_end(date):
        tds += SCORE_TDS_QUARTER_END
        dbg.append("Transaction occurred at quarter-end")

    # ── GST scoring ───────────────────────────────────────────────────────────
    gst = 0

    if _RE_GSTIN.search(text.upper()):
        gst += SCORE_GST_GSTIN_PATTERN
        result.classification_mode = "EXPLICIT"
        dbg.append("Explicit GSTIN pattern detected")

    for kw, pattern in _RE_GST_KEYWORDS:
        if pattern.search(text):
            gst += SCORE_GST_KEYWORD
            result.classification_mode = "EXPLICIT"
            dbg.append("Explicit GST keyword found")
            break

    for kw in _MERCHANT_SET:
        if kw in text:
            gst += SCORE_GST_GATEWAY
            dbg.append("Possible business/merchant payment inferred")
            break

    if tx_type in (TxType.CMS, TxType.CARD_PAYMENT):
        gst += SCORE_GST_CMS_CARDPMT
        dbg.append("Possible business expense inferred from card payment")

    if tx_type == TxType.UPI_DEBIT:
        gst += SCORE_GST_UPI_DEBIT
        dbg.append("Possible merchant/business payment inferred from UPI narration")

    if debit > 0 and _is_nonround(debit):
        gst += SCORE_GST_NONROUND_AMT
        dbg.append("Non-round fractional amount")

    # ── Negative penalties ────────────────────────────────────────────────────
    neg     = _negative_penalty(text, dbg)        # both TDS and GST
    neg_tds = _company_suffix_penalty(text, dbg)  # TDS only
    tds = max(0, tds + neg + neg_tds)
    gst = max(0, gst + neg)

    # ── Direction penalty — incoming credits ──────────────────────────────────
    is_incoming = (credit > 0 and debit == 0)
    if is_incoming:
        is_refund = "refund" in text
        if not (is_refund and gst > 0):
            gst = max(0, gst + PENALTY_INCOMING_GST)
            dbg.append("Incoming credit penalty applied to GST")
        
        # Exception: if we found strong TDS keywords/sections, do not penalize
        if not (tds >= 8 or is_refund):
            tds = max(0, tds + PENALTY_INCOMING_TDS)
            dbg.append("Incoming credit penalty applied to TDS")

    result.tds_score = tds
    result.gst_score = gst

    # ── Category decision ─────────────────────────────────────────────────────
    # Priority 1: Strong TDS — unless a primary GST keyword present
    if tds >= SCORE_HIGH_THRESHOLD and not has_strong_gst:
        result.category = CATEGORY_TDS
        dbg.append(f"TDS high tds={tds} ≥ {SCORE_HIGH_THRESHOLD}")

    # Priority 2: High-confidence GST
    elif gst >= SCORE_HIGH_THRESHOLD:
        result.category = CATEGORY_GST
        dbg.append(f"GST high gst={gst}")

    # Priority 3: Medium TDS wins over medium GST
    elif tds >= SCORE_MEDIUM_THRESHOLD and tds >= gst:
        result.category = CATEGORY_TDS
        dbg.append(f"TDS medium tds={tds}")

    # Priority 4: Medium GST
    elif gst >= SCORE_MEDIUM_THRESHOLD:
        result.category = CATEGORY_GST
        dbg.append(f"GST medium gst={gst}")

    # Priority 5: Soft GST — positive GST score, no competing TDS
    elif gst > 0:
        result.category = CATEGORY_GST
        dbg.append(f"GST soft gst={gst}")

    # Priority 6: UNCERTAIN — ONLY when BOTH scores have meaningful competing
    # signals (both ≥ SCORE_UNCERTAIN_CUTOFF). Avoids false UNCERTAIN for
    # low-signal transactions that should simply be NORMAL.
    elif tds >= SCORE_UNCERTAIN_CUTOFF and gst >= SCORE_UNCERTAIN_CUTOFF:
        result.category = CATEGORY_UNCERTAIN
        dbg.append(f"UNCERTAIN — competing signals tds={tds} gst={gst}")

    # Priority 7: Soft vendor override (SOFT priority, no strong tax signal)
    elif vendor_override_cat == CATEGORY_NORMAL and vendor_override_prio == "SOFT":
        result.category = CATEGORY_NORMAL
        dbg.append("SOFT vendor override applied → NORMAL")

    # Default: no meaningful signals → NORMAL
    else:
        result.category = CATEGORY_NORMAL
        dbg.append(f"NORMAL — no signals tds={tds} gst={gst}")

    return _finalise(result, debit, credit, amount, dbg)


# ── Finalise: confidence + Needs_Review + Reason ─────────────────────────────

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

    # ── Map Heuristic GST to POSSIBLE_GST ─────────────────────────────────────
    if result.category == CATEGORY_GST and result.classification_mode == "HEURISTIC":
        result.category = CATEGORY_POSSIBLE_GST

    # Needs_Review
    # Trigger ONLY if:
    # 1. Multiple competing signals (UNCERTAIN)
    # 2. Medium confidence with a small score gap
    is_tax = result.category in (CATEGORY_GST, CATEGORY_POSSIBLE_GST, CATEGORY_TDS)
    score_gap = abs(tds - gst)

    result.needs_review = (
        result.category == CATEGORY_UNCERTAIN
        or (is_tax and (result.confidence == "LOW" or (result.confidence == "MEDIUM" and score_gap <= SCORE_CLOSE_CALL_MARGIN)))
    )

    # ── Reason string — human-readable, pipe-separated signal list ────────────
    # Clean up empty strings and remove duplicates while preserving order
    clean_dbg = []
    for d in dbg:
        if d and d not in clean_dbg:
            clean_dbg.append(d)
            
    result.reason = " | ".join(clean_dbg) if clean_dbg else "No distinct signals found"

    logger.debug(
        "[%s|%s|review=%s] tds=%d gst=%d | %s",
        result.category, result.confidence, result.needs_review,
        tds, gst, result.reason,
    )
    return result


# ── Private helpers ───────────────────────────────────────────────────────────

def _safe_float(val) -> float:
    """Convert val to float, returning 0.0 for None / NaN / unconvertible values."""
    try:
        v = float(val)
        return 0.0 if v != v else v   # v != v is True only for NaN
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
    matched = False
    for pattern, penalty in _NEGATIVE_PATTERNS:
        if pattern.search(text):
            total += penalty
            matched = True
    if matched:
        dbg.append("Matched personal/transfer exclusion keyword")
    return total


def _company_suffix_penalty(text: str, dbg: list) -> int:
    """Penalty applied to TDS score ONLY — not GST."""
    total = 0
    matched = False
    for pattern, penalty in _COMPANY_SUFFIX_PATTERNS:
        if pattern.search(text):
            total += penalty
            matched = True
    if matched:
        dbg.append("Company suffix penalty applied")
    return total
