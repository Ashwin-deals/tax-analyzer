# ─────────────────────────────────────────────────────────────────────────────
#  utils/constants.py  —  Single source of truth for keywords, weights, paths
# ─────────────────────────────────────────────────────────────────────────────

# ── Internal column aliases ───────────────────────────────────────────────────
# Added to the DataFrame by normalize_columns(); dropped before export.
INTERNAL_DESCRIPTION_COL = "_description"
INTERNAL_DEBIT_COL       = "_debit"
INTERNAL_CREDIT_COL      = "_credit"
INTERNAL_DATE_COL        = "_date"
INTERNAL_COLS = [INTERNAL_DESCRIPTION_COL, INTERNAL_DEBIT_COL,
                 INTERNAL_CREDIT_COL, INTERNAL_DATE_COL]

# ── Column name candidates (case-insensitive auto-detection) ──────────────────
DESCRIPTION_COLUMN_CANDIDATES = [
    "particulars", "narration", "description", "remarks",
    "transaction details", "details", "transaction narration", "reference",
]
DEBIT_COLUMN_CANDIDATES = [
    "debit", "withdrawal", "withdrawal amt.", "withdrawal amt",
    "debit amt", "debit amt.", "dr amount", "dr amt",
]
CREDIT_COLUMN_CANDIDATES = [
    "credit", "deposit", "deposit amt.", "deposit amt",
    "credit amt", "credit amt.", "cr amount", "cr amt",
]
DATE_COLUMN_CANDIDATES = [
    "transaction date", "date", "value date", "txn date", "posting date",
]

# ── Categories ────────────────────────────────────────────────────────────────
CATEGORY_TDS       = "TDS"
CATEGORY_GST       = "GST"
CATEGORY_NORMAL    = "NORMAL"
CATEGORY_UNCERTAIN = "UNCERTAIN"

# Thresholds recalibrated: UNCERTAIN is only for genuinely ambiguous mid-range scores.
# Score=0 on both → NORMAL. Score 1-2 → NORMAL. Score 3-7 → possible UNCERTAIN.
SCORE_HIGH_THRESHOLD     = 8    # ≥ 8  → HIGH confidence, direct classification
SCORE_MEDIUM_THRESHOLD   = 3    # ≥ 3  → MEDIUM confidence, classifiable
SCORE_UNCERTAIN_CUTOFF   = 3    # only used for truly ambiguous mid-range (3–5)
SCORE_CLOSE_CALL_MARGIN  = 2    # TDS/GST within this margin → Needs_Review

# ── TDS signal weights ────────────────────────────────────────────────────────
SCORE_TDS_KEYWORD        = 10
SCORE_TDS_SECTION_CODE   = 8
SCORE_TDS_TXTYPE_BLKNEFT = 4
SCORE_TDS_QUARTER_END    = 2

# ── GST signal weights ────────────────────────────────────────────────────────
SCORE_GST_KEYWORD        = 10
SCORE_GST_GSTIN_PATTERN  = 9
SCORE_GST_GATEWAY        = 6
SCORE_GST_CMS_CARDPMT    = 5    # CMS_ / CARD PAYMENT tx type (Fix #4)
SCORE_GST_UPI_DEBIT      = 3    # UPI/DR/ outgoing — reduced to avoid P2P false positives
SCORE_GST_NONROUND_AMT   = 2

# Applied symmetrically when a transaction is a pure incoming credit (Fix #5)
PENALTY_INCOMING_TDS = -5
PENALTY_INCOMING_GST = -5

# ── Amount sanity thresholds ──────────────────────────────────────────────────
AMOUNT_IGNORE_BELOW = 1.0          # < ₹1  → skip TDS/GST scoring
AMOUNT_FLAG_ABOVE   = 1_000_000.0  # > ₹10L → flag for review unless strong signal

# ── Soft negative keyword penalties (Fix #6) ─────────────────────────────────
# Each tuple: (pattern_string, is_regex, penalty_points)
# Penalties are SUBTRACTED from both TDS and GST scores (not a hard cancel).
NEGATIVE_KEYWORDS = [
    (r"upi/cr/",           False, -6),   # UPI incoming credit — money received
    (r"setdt-",            False, -5),   # Settlement date suffix in card narrations
    (r"imps-opm/",         False, -4),   # Standard IMPS transfer prefix
    (r"/p2p/",             False, -7),   # Peer-to-peer UPI transfer
    (r"\batm[/ ]",         True,  -8),   # ATM withdrawal
    (r"birthday",          False, -6),   # Personal gift transfer
    (r"interest credit",   False, -5),   # Savings interest credit, not GST
    (r"salary credit",     False, -5),   # Salary receipt, not TDS/GST
    (r"personal",          False, -3),   # Personal transfer hint
    (r"credit card bill",  False, -7),   # Credit card bill payment = bank transfer, not GST
    (r"card bill payment", False, -7),   # Same — axis/hdfc card bill
    (r"petrol",            False, -4),   # Petrol/fuel — personal expense, not merchant GST
    (r"fuel fill",         False, -4),   # Fuel station — personal
    (r"loan emi",          False, -5),   # Loan EMI = normal bank payment
    (r"insurance premium", False, -4),   # Insurance = normal payment
    (r"school fee",        False, -4),   # School fee = normal payment
]

# ── TDS keywords (whole-word matched in classifier) ───────────────────────────
TDS_KEYWORDS = [
    "tds", "tax deducted", "tax deducted at source",
    "tds deduction", "tds credit", "tds recovery",
    "income tax", "it refund", "it demand", "tcs",
]

# TDS section codes — matched with letter suffix (194A) OR next to tds/section
TDS_SECTION_CODES = ["192", "193", "194", "195", "196", "206"]

# ── GST keywords — NO bare "tax" (Fix #12) ────────────────────────────────────
# "tax" alone is too broad; "income tax" is TDS. Only compound GST terms here.
GST_KEYWORDS = [
    "gst", "cgst", "sgst", "igst", "utgst", "gstin",
    "gst payment", "gst refund", "gst credit", "gst reversal",
    "gst challan", "gst payable",
    "goods and service", "goods & service",
    "service tax",      # pre-GST era
    "tax invoice",      # compound — acceptable
    "proforma invoice", "e-invoice", "einvoice",
    "invoice", "bill payment",
]

# ── Merchant / payment-gateway keywords (→ GST) ───────────────────────────────
MERCHANT_KEYWORDS = [
    "card pmt", "card payment", "credit card pmt", "debit card pmt",
    "point of sale", "cms_", "neft/gst", "rtgs/gst",
    "purchase", "vendor payment", "merchant",
    "swiggy", "zomato", "amazon", "flipkart", "myntra",
    "paytm", "phonepe", "gpay", "google pay",
    "razorpay", "payu", "ccavenue", "easebuzz", "billdesk",
]

# ── Category → header colour (openpyxl ARGB) ─────────────────────────────────
CATEGORY_COLOURS = {
    CATEGORY_TDS:       "FFFFC000",  # amber
    CATEGORY_GST:       "FF70AD47",  # green
    CATEGORY_NORMAL:    "FF4472C4",  # blue
    CATEGORY_UNCERTAIN: "FFD9D9D9",  # light grey
    "SUMMARY":          "FF7030A0",  # purple
}

# ── Paths ─────────────────────────────────────────────────────────────────────
DEFAULT_INPUT_PATH = "data/input/bank_statement.xlsx"
DEFAULT_OUTPUT_DIR = "data/output"
OUTPUT_FILENAMES = {
    CATEGORY_GST:       "gst_transactions.xlsx",
    CATEGORY_TDS:       "tds_transactions.xlsx",
    CATEGORY_NORMAL:    "normal_transactions.xlsx",
    CATEGORY_UNCERTAIN: "uncertain_transactions.xlsx",
}
SUMMARY_FILENAME = "classification_summary.xlsx"