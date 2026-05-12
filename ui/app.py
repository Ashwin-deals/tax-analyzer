"""
ui/app.py
─────────
Streamlit web UI for the Bank Statement GST & TDS Classifier.

Supports two input modes:
  1. Manual upload  — user uploads an .xlsx bank statement file
  2. Gmail fetch    — system connects to Gmail and downloads the latest
                      statement attachment automatically

Run from project root:
    streamlit run ui/app.py
"""

import io
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Project root on sys.path ──────────────────────────────────────────────────
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.loader import load_excel
from src.processor import process_transactions
from utils.constants import (
    CATEGORY_GST, CATEGORY_NORMAL, CATEGORY_TDS, CATEGORY_POSSIBLE_GST,
)
from utils.email_utils import is_configured, load_credentials, mask_email

logging.basicConfig(level=logging.WARNING)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bank Statement Analyzer",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    #MainMenu, footer          { visibility: hidden; }

    /* ── Header ── */
    .app-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin-bottom: 1.5rem;
        color: white;
    }
    .app-header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
    .app-header p  { margin: 0.4rem 0 0; opacity: 0.75; font-size: 1rem; }

    /* ── Metric cards ── */
    .metric-card {
        background: white;
        border-radius: 14px;
        padding: 1.3rem 1.5rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        border-left: 5px solid #ccc;
        text-align: center;
    }
    .metric-card .label {
        font-size: 0.78rem; font-weight: 600;
        letter-spacing: 0.08em; text-transform: uppercase;
        color: #6b7280; margin-bottom: 0.5rem;
    }
    .metric-card .value { font-size: 2.2rem; font-weight: 800; line-height: 1; }

    .card-total   { border-left-color: #6366f1; }  .card-total   .value { color: #6366f1; }
    .card-gst     { border-left-color: #22c55e; }  .card-gst     .value { color: #22c55e; }
    .card-possible_gst { border-left-color: #84cc16; } .card-possible_gst .value { color: #84cc16; }
    .card-business_payment { border-left-color: #f97316; } .card-business_payment .value { color: #f97316; }
    .card-tds     { border-left-color: #f59e0b; }  .card-tds     .value { color: #f59e0b; }
    .card-normal  { border-left-color: #3b82f6; }  .card-normal  .value { color: #3b82f6; }
    .card-uncertain { border-left-color: #9ca3af; } .card-uncertain .value { color: #9ca3af; }

    /* ── Gmail status badge ── */
    .env-badge {
        display: inline-flex; align-items: center; gap: 0.5rem;
        padding: 0.45rem 1rem;
        border-radius: 999px;
        font-size: 0.82rem; font-weight: 600;
    }
    .env-ok   { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .env-miss { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }

    /* ── Setup card ── */
    .setup-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1.5rem 2rem;
        margin-top: 0.5rem;
    }
    .setup-card code {
        background: #1e293b; color: #e2e8f0;
        padding: 0.8rem 1.2rem;
        border-radius: 8px;
        display: block;
        font-size: 0.85rem;
        line-height: 1.7;
        white-space: pre;
    }

    /* ── Upload zone ── */
    .upload-zone {
        border: 2px dashed #d1d5db; border-radius: 14px;
        padding: 2rem; text-align: center;
        background: #f9fafb; margin-bottom: 1rem;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1.2rem; font-weight: 600;
    }

    .stDownloadButton > button { border-radius: 8px; font-weight: 600; }
    hr { margin: 1.2rem 0; }
</style>
""", unsafe_allow_html=True)


# ── App header ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>🏦 Bank Statement Analyzer</h1>
    <p>Explainable financial transaction intelligence: flow behavior plus GST · POSSIBLE GST · TDS · NORMAL tax interpretation</p>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()


def _card(label: str, value: int, css_class: str) -> str:
    return f"""
    <div class="metric-card {css_class}">
        <div class="label">{label}</div>
        <div class="value">{value:,}</div>
    </div>"""


def _render_tab(df: pd.DataFrame, category: str, download_name: str):
    if df.empty:
        st.info(f"No {category} transactions found.")
        return

    if "REVIEW_RECOMMENDED" in df.columns:
        review_col = "REVIEW_RECOMMENDED"
    elif "Review_Recommended" in df.columns:
        review_col = "Review_Recommended"
    else:
        review_col = "Needs_Review"
    review_count = int(df[review_col].sum()) if review_col in df.columns else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Transactions", f"{len(df):,}")
    if "Debit" in df.columns:
        c2.metric("Total Debit (₹)", f"{pd.to_numeric(df['Debit'], errors='coerce').sum():,.2f}")
    if review_count:
        c3.metric("⚠️ Review Recommended", review_count)

    st.divider()

    hide = {"_description", "_debit", "_credit", "_date", "FLOW_TYPE", "Flow_Type"}
    show_cols = [c for c in df.columns if c not in hide]

    ml_col = "ML_ASSIST" if "ML_ASSIST" in show_cols else "ML_Assist" if "ML_Assist" in show_cols else None
    if ml_col and not df[ml_col].replace("N/A", pd.NA).dropna().any():
        show_cols.remove(ml_col)

    # Reorder around the simplified semantic output columns.
    priority_cols = ["TAX_CATEGORY", "CONFIDENCE", "REVIEW_RECOMMENDED",
                     "ML_ASSIST", "REASON"]
    ordered = [c for c in priority_cols if c in show_cols]
    rest = [c for c in show_cols if c not in priority_cols]
    show_cols = rest[:3] + ordered + rest[3:]  # keep narration/date/amount first

    col_cfg = {}
    if "REASON" in show_cols:
        col_cfg["REASON"] = st.column_config.TextColumn(
            "Reason", width="large",
            help="Signal chain that led to the classification"
        )
    if "REVIEW_RECOMMENDED" in show_cols:
        col_cfg["REVIEW_RECOMMENDED"] = st.column_config.CheckboxColumn(
            "Review Recommended",
            help="Advisory flag for ambiguous, low-confidence, or ML-uncertain classifications."
        )
    if "TAX_CATEGORY" in show_cols:
        col_cfg["TAX_CATEGORY"] = st.column_config.TextColumn(
            "Tax Category", width="medium",
            help="Tax interpretation: GST, POSSIBLE_GST, TDS, or NORMAL."
        )
    if "ML_ASSIST" in show_cols:
        col_cfg["ML_ASSIST"] = st.column_config.TextColumn(
            "ML Assist", width="small",
            help="Calibrated ML probability shown only when ML changed the tax interpretation"
        )

    st.dataframe(df[show_cols], width="stretch",
                 height=min(600, max(200, (len(df) + 1) * 36)),
                 column_config=col_cfg)

    st.divider()
    st.download_button(
        label=f"⬇️  Download {category} transactions",
        data=_to_excel_bytes(df[show_cols]),
        file_name=download_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _render_results(result: dict, source_label: str):
    """Render the full classification output: success banner, cards, tabs."""
    gst_df           = result.get(CATEGORY_GST,              pd.DataFrame())
    possible_gst_df  = result.get(CATEGORY_POSSIBLE_GST,     pd.DataFrame())
    tds_df           = result.get(CATEGORY_TDS,              pd.DataFrame())
    normal_df        = result.get(CATEGORY_NORMAL,           pd.DataFrame())
    total = len(gst_df) + len(possible_gst_df) + len(tds_df) + len(normal_df)

    st.success(f"✅ Classified **{total:,} transactions** from `{source_label}`")
    st.divider()

    # Summary cards
    st.markdown("### 📊 Classification Summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(_card("Total",        total,                "card-total"),          unsafe_allow_html=True)
    c2.markdown(_card("GST",          len(gst_df),          "card-gst"),            unsafe_allow_html=True)
    c3.markdown(_card("Poss GST",     len(possible_gst_df), "card-possible_gst"),   unsafe_allow_html=True)
    c4.markdown(_card("TDS",          len(tds_df),          "card-tds"),            unsafe_allow_html=True)
    c5.markdown(_card("Normal",       len(normal_df),       "card-normal"),         unsafe_allow_html=True)

    st.divider()

    # Review banner
    all_dfs = [gst_df, possible_gst_df, tds_df, normal_df]
    review_total = sum(
        int(df["REVIEW_RECOMMENDED"].sum())
        for df in all_dfs
        if not df.empty and "REVIEW_RECOMMENDED" in df.columns
    )
    if review_total:
        st.warning(
            f"⚠️ **Global Review Total: {review_total} transactions** across all categories are suggested for manual verification. "
            "Review recommendations are advisory and usually occur for LOW-confidence or ambiguous classifications."
        )

    # Result tabs
    st.markdown("### 📋 Classified Transactions")
    t_gst, t_pgst, t_tds, t_normal = st.tabs([
        f"🟢  GST  ({len(gst_df):,})",
        f"🟩  POSSIBLE GST  ({len(possible_gst_df):,})",
        f"🟡  TDS  ({len(tds_df):,})",
        f"🔵  NORMAL  ({len(normal_df):,})",
    ])
    with t_gst:      _render_tab(gst_df,          "GST",              "gst_transactions.xlsx")
    with t_pgst:     _render_tab(possible_gst_df, "POSSIBLE GST",     "possible_gst_transactions.xlsx")
    with t_tds:      _render_tab(tds_df,          "TDS",              "tds_transactions.xlsx")
    with t_normal:   _render_tab(normal_df,       "NORMAL",           "normal_transactions.xlsx")

def _update_learning_memory(pattern: str, category: str):
    import csv
    mem_path = Path(__file__).resolve().parent.parent / "data" / "learning_memory.csv"
    
    rows = []
    found = False
    if mem_path.exists():
        with mem_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("vendor_pattern") == pattern and row.get("corrected_category") == category:
                    row["count"] = str(int(row.get("count", 0)) + 1)
                    found = True
                rows.append(row)
                
    if not found:
        rows.append({"vendor_pattern": pattern, "corrected_category": category, "count": "1"})
        
    with mem_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["vendor_pattern", "corrected_category", "count"])
        writer.writeheader()
        writer.writerows(rows)

    # ── Vendor Learning UI ────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 🧠 Train Vendor Memory")
    st.write("Help the system learn! If a vendor is consistently misclassified, submit a correction below.")
    
    with st.expander("Submit Vendor Correction"):
        with st.form("train_memory_form"):
            col1, col2 = st.columns(2)
            with col1:
                vendor_input = st.text_input("Vendor Pattern (e.g., 'RAZORPAY', 'SWIGGY', 'TNEB')", help="A unique word or phrase found in the transaction narration.")
            with col2:
                corrected_cat = st.selectbox("Correct Tax Category", ["NORMAL", "GST", "POSSIBLE_GST", "TDS"])
            
            if st.form_submit_button("Train System"):
                if vendor_input.strip():
                    _update_learning_memory(vendor_input.strip().lower(), corrected_cat)
                    from src.scorer import reload_memory
                    from src.ml_pipeline import log_user_correction
                    reload_memory()
                    log_user_correction(vendor_input.strip(), corrected_cat)
                    st.success(f"✅ Learned! '{vendor_input}' is now biased towards {corrected_cat}. Re-run the classification to see changes.")
                else:
                    st.error("Please enter a vendor pattern.")


def _run_pipeline(file_path: Path) -> dict:
    """Load and classify a statement file. Returns categorised result dict."""
    df_raw = load_excel(file_path)
    return process_transactions(df_raw)


# ══════════════════════════════════════════════════════════════════════════════
# Mode selector
# ══════════════════════════════════════════════════════════════════════════════

mode_upload, mode_gmail = st.tabs([
    "📤  Upload File",
    "📧  Fetch from Gmail",
])


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Manual Upload
# ══════════════════════════════════════════════════════════════════════════════

with mode_upload:
    st.markdown("### 📂 Upload Bank Statement")

    uploaded = st.file_uploader(
        label="",
        type=["xlsx"],
        help="Upload your bank statement in .xlsx format",
        label_visibility="collapsed",
        key="file_uploader",
    )

    if uploaded is None:
        st.markdown("""
        <div class="upload-zone">
            <h3 style="color:#6b7280;margin:0">Drop your .xlsx bank statement here</h3>
            <p style="color:#9ca3af;margin:0.5rem 0 0">Supports IDFC, HDFC, Axis, SBI, Kotak formats</p>
        </div>
        """, unsafe_allow_html=True)

    else:
        with st.spinner("🔄 Processing your bank statement…"):
            tmp_path = None
            try:
                suffix = Path(uploaded.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded.read())
                    tmp_path = Path(tmp.name)

                result = _run_pipeline(tmp_path)

            except SystemExit as e:
                st.error(f"❌ Could not load file: {e}")
                st.stop()
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
                st.stop()
            finally:
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)

        _render_results(result, uploaded.name)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Gmail Fetch
# ══════════════════════════════════════════════════════════════════════════════

with mode_gmail:
    st.markdown("### 📧 Fetch Statement from Gmail")

    # ── Credential status ─────────────────────────────────────────────────────
    env_ok = is_configured()

    if env_ok:
        try:
            email_addr, _ = load_credentials()
            st.markdown(
                f'<span class="env-badge env-ok">✅ Gmail configured — {mask_email(email_addr)}</span>',
                unsafe_allow_html=True,
            )
        except Exception:
            st.markdown(
                '<span class="env-badge env-miss">❌ Credentials not set</span>',
                unsafe_allow_html=True,
            )
            env_ok = False
    else:
        st.markdown(
            '<span class="env-badge env-miss">❌ Credentials not configured</span>',
            unsafe_allow_html=True,
        )

    # ── Setup instructions (shown when .env is missing) ───────────────────────
    if not env_ok:
        st.markdown("""
        <div class="setup-card">
            <h4 style="margin:0 0 0.75rem">⚙️ One-time setup required</h4>
            <p style="margin:0 0 0.75rem; color:#475569">
                Create a <strong>.env</strong> file in the project root:
            </p>
            <code>EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_16_char_app_password</code>
            <p style="margin:0.9rem 0 0; color:#64748b; font-size:0.85rem">
                ⚠️ Use a <strong>Gmail App Password</strong>, not your regular password.<br>
                Generate one at: <em>Google Account → Security → 2-Step Verification → App Passwords</em>
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # ── Fetch controls ────────────────────────────────────────────────────────
    st.markdown("")

    col_left, col_right = st.columns([2, 1])
    with col_left:
        max_emails = st.slider(
            "Max emails to scan",
            min_value=5, max_value=50, value=20, step=5,
            help="How many recent statement-subject emails to inspect for attachments.",
        )

    with col_right:
        st.markdown("<div style='margin-top:1.6rem'></div>", unsafe_allow_html=True)
        fetch_clicked = st.button(
            "🔄  Fetch Latest Statement",
            use_container_width=True,
            type="primary",
        )

    if fetch_clicked:
        _output_dir = _root / "data" / "email_statements"

        with st.spinner("📬 Connecting to Gmail and scanning for statement attachments…"):
            try:
                from src.email_fetcher import GmailFetchError, fetch_statements

                email_addr, app_password = load_credentials()
                downloaded = fetch_statements(
                    email_address=email_addr,
                    app_password=app_password,
                    output_dir=_output_dir,
                    max_emails=max_emails,
                )

            except GmailFetchError as exc:
                st.error(f"❌ Gmail connection failed: {exc}")
                st.stop()
            except ValueError as exc:
                st.error(f"❌ Credential error: {exc}")
                st.stop()
            except Exception as exc:
                st.error(f"❌ Unexpected error during fetch: {exc}")
                st.stop()

        if not downloaded:
            st.warning(
                "📭 No statement attachments found in your unread emails.\n\n"
                "**Check:**\n"
                "- The statement email is **unread** in Gmail — already-read emails are skipped\n"
                "- The subject contains 'statement', 'bank statement', 'account statement', "
                "or 'monthly statement'\n"
                "- The attachment is a `.xlsx` or `.xls` file\n"
                "- IMAP access is enabled in Gmail → Settings → Forwarding and POP/IMAP"
            )
            st.stop()

        # ── Process the most-recent downloaded file ───────────────────────────
        latest_file = downloaded[0]

        if len(downloaded) > 1:
            st.info(
                f"📎 Found **{len(downloaded)} attachment(s)**. "
                f"Processing the most recent: `{latest_file.name}`"
            )

        with st.spinner(f"⚙️ Classifying `{latest_file.name}`…"):
            try:
                result = _run_pipeline(latest_file)
            except SystemExit as e:
                st.error(f"❌ Could not load statement: {e}")
                st.stop()
            except Exception as e:
                st.error(f"❌ Error during classification: {e}")
                st.stop()

        _render_results(result, latest_file.name)

        # Show all downloaded files in an expander
        if len(downloaded) > 1:
            with st.expander(f"📁 All {len(downloaded)} downloaded files"):
                for p in downloaded:
                    st.markdown(f"- `{p.name}` — {p.stat().st_size / 1024:.1f} KB")
