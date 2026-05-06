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
    CATEGORY_GST, CATEGORY_NORMAL, CATEGORY_TDS, CATEGORY_UNCERTAIN,
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
    <p>Classify transactions into GST · TDS · NORMAL — upload manually or fetch directly from Gmail</p>
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

    review_count = int(df["Needs_Review"].sum()) if "Needs_Review" in df.columns else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Transactions", f"{len(df):,}")
    if "Debit" in df.columns:
        c2.metric("Total Debit (₹)", f"{pd.to_numeric(df['Debit'], errors='coerce').sum():,.2f}")
    if review_count:
        c3.metric("⚠️ Needs Review", review_count)

    st.divider()

    hide = {"Needs_Review", "_description", "_debit", "_credit", "_date"}
    show_cols = [c for c in df.columns if c not in hide]
    st.dataframe(df[show_cols], use_container_width=True,
                 height=min(600, max(200, (len(df) + 1) * 36)))

    st.divider()
    st.download_button(
        label=f"⬇️  Download {category} transactions",
        data=_to_excel_bytes(df[show_cols]),
        file_name=download_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _render_results(result: dict, source_label: str):
    """Render the full classification output: success banner, cards, tabs."""
    gst_df       = result.get(CATEGORY_GST,      pd.DataFrame())
    tds_df       = result.get(CATEGORY_TDS,      pd.DataFrame())
    normal_df    = result.get(CATEGORY_NORMAL,   pd.DataFrame())
    uncertain_df = result.get(CATEGORY_UNCERTAIN, pd.DataFrame())
    total        = len(gst_df) + len(tds_df) + len(normal_df) + len(uncertain_df)

    st.success(f"✅ Classified **{total:,} transactions** from `{source_label}`")
    st.divider()

    # Summary cards
    st.markdown("### 📊 Classification Summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(_card("Total",     total,           "card-total"),     unsafe_allow_html=True)
    c2.markdown(_card("GST",       len(gst_df),     "card-gst"),       unsafe_allow_html=True)
    c3.markdown(_card("TDS",       len(tds_df),     "card-tds"),       unsafe_allow_html=True)
    c4.markdown(_card("Normal",    len(normal_df),  "card-normal"),    unsafe_allow_html=True)
    c5.markdown(_card("Uncertain", len(uncertain_df), "card-uncertain"), unsafe_allow_html=True)

    st.divider()

    # Review banner
    all_dfs = [gst_df, tds_df, normal_df, uncertain_df]
    review_total = sum(
        int(df["Needs_Review"].sum())
        for df in all_dfs
        if not df.empty and "Needs_Review" in df.columns
    )
    if review_total:
        st.warning(
            f"⚠️ **{review_total} transactions** flagged for manual review. "
            "Check the **Needs_Review** column in each tab."
        )

    # Result tabs
    st.markdown("### 📋 Classified Transactions")
    t_gst, t_tds, t_normal, t_uncertain = st.tabs([
        f"🟢  GST  ({len(gst_df):,})",
        f"🟡  TDS  ({len(tds_df):,})",
        f"🔵  NORMAL  ({len(normal_df):,})",
        f"⚪  UNCERTAIN  ({len(uncertain_df):,})",
    ])
    with t_gst:      _render_tab(gst_df,       "GST",       "gst_transactions.xlsx")
    with t_tds:      _render_tab(tds_df,       "TDS",       "tds_transactions.xlsx")
    with t_normal:   _render_tab(normal_df,    "NORMAL",    "normal_transactions.xlsx")
    with t_uncertain: _render_tab(uncertain_df, "UNCERTAIN", "uncertain_transactions.xlsx")


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
                "📭 No statement attachments found in your recent emails.\n\n"
                "**Check:**\n"
                "- Your bank emails the statement with subject containing "
                "'statement', 'bank statement', 'account statement', or 'monthly statement'\n"
                "- The attachment is a `.xlsx` or `.xls` file\n"
                "- IMAP access is enabled in your Gmail settings"
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
