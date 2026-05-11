import re
import math
import pandas as pd
from typing import Optional

def extract_vendor(narration: str) -> str:
    """
    Utility for vendor extraction from normalized text.
    To be used in future ML feature pipelines.
    """
    # Try common UPI patterns
    m = re.search(r"upi/dr/[^/]+/([^/]+)/", narration, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    
    # Try known gateways
    m = re.search(r"(razorpay|bharatpe|swiggy|zomato|amazon|paytm|cms_ift)", narration, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    
    # Fallback to first word chunk
    parts = narration.split()
    return parts[0].upper()[:15] if parts else ""

def compute_amount_features(debit: float, credit: float) -> dict:
    """
    Extract amount-based features for ML models.
    """
    amt = debit if debit > 0 else credit
    is_round = (amt % 100 == 0) and amt > 0
    return {
        "amount": amt,
        "is_debit": 1 if debit > 0 else 0,
        "is_credit": 1 if credit > 0 else 0,
        "is_round_amount": 1 if is_round else 0,
        "log_amount": math.log1p(amt) if amt > 0 else 0
    }

def build_heuristic_vector(gst_score: int, tds_score: int) -> list[int]:
    """
    Format heuristic scores as ML vectors.
    """
    return [gst_score, tds_score]

def compute_vendor_frequency(vendor: str, history_df: pd.DataFrame) -> int:
    """
    Compute how many times a vendor has appeared in the historical dataset.
    """
    if history_df.empty or not vendor:
        return 0
    return int((history_df['vendor'] == vendor).sum())
