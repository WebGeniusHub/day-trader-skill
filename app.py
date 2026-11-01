import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
TRADER = ROOT / "trader"
WATCHLIST = TRADER / "watchlist.json"

st.set_page_config(
    page_title="NEXUS | Market Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Visual system ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');

:root {
  --bg: #070b12;
  --panel: rgba(15, 24, 38, .78);
  --panel-strong: #101b2a;
  --line: rgba(139, 169, 202, .15);
  --muted: #8495aa;
  --text: #eaf2fb;
  --cyan: #4de5d0;
  --blue: #6c9cff;
  --violet: #a58bff;
}
html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }
.stApp {
  color: var(--text);
  background:
    radial-gradient(ellipse at 12% 0%, rgba(31, 112, 132, .18), transparent 34%),
    radial-gradient(ellipse at 92% 12%, rgba(92, 74, 166, .17), transparent 32%),
    linear-gradient(145deg, #070b12 0%, #0a111c 48%, #080d16 100%);
}
[data-testid="stHeader"] { background: rgba(7, 11, 18, .78); }
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0b1421 0%, #0a101a 100%);
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] > div { padding-top: 1.6rem; }
.block-container { max-width: 1480px; padding-top: 2.1rem; padding-bottom: 3rem; }
h1, h2, h3, p, label { color: var(--text); }
h1 { letter-spacing: -.055em; font-weight: 800; }
h2, h3 { letter-spacing: -.035em; font-weight: 700; }
small, .muted { color: var(--muted); }
code, .stCode, [data-testid="stMetricValue"] { font-family: 'DM Mono', monospace; }
[data-testid="stMetric"] {
  background: linear-gradient(145deg, rgba(18, 31, 48, .94), rgba(12, 21, 34, .88));
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 18px 20px;
  box-shadow: 0 12px 34px rgba(0,0,0,.16);
}
[data-testid="stMetricLabel"] { color: #8fa4bb; font-size: .76rem; text-transform: uppercase; letter-spacing: .12em; }
[data-testid="stMetricValue"] { color: #f2f8ff; font-size: 1.65rem; }
.stButton > button, .stDownloadButton > button {
  border: 1px solid rgba(77,229,208,.38);
  border-radius: 11px;
  min-height: 2.8rem;
  background: linear-gradient(110deg, rgba(37,177,164,.20), rgba(92,126,224,.22));
  color: #eafffc;
  font-weight: 800;
  letter-spacing: .015em;
  transition: all .18s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--cyan);
  color: white;
  box-shadow: 0 0 24px rgba(77,229,208,.15);
  transform: translateY(-1px);
}
.stTabs [data-baseweb="tab-list"] {
  gap: 8px;
  border-bottom: 1px solid var(--line);
  background: rgba(11, 19, 31, .55);
  padding: 7px;
  border-radius: 13px;
}
.stTabs [data-baseweb="tab"] {
  height: 44px;
  border-radius: 9px;
  color: #91a2b7;
  font-weight: 700;
  background: transparent;
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(110deg, rgba(77,229,208,.16), rgba(108,156,255,.16));
  color: #eafffc !important;
}
[data-testid="stDataFrame"] {
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
}
[data-baseweb="input"], [data-baseweb="select"], [data-testid="stSelectSlider"] {
  background: rgba(13, 23, 37, .85);
}
hr { border-color: var(--line); }
div[data-testid="stAlert"] { border-radius: 12px; }
div[data-testid="stExpander"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: rgba(13, 23, 37, .65);
}
.nx-brand {
  color: #eaf7ff; font-size: 1.02rem; font-weight: 800;
  letter-spacing: .2em; text-transform: uppercase;
}
.nx-brand span { color: var(--cyan); }
.nx-kicker {
  color: var(--cyan); font: 500 .72rem 'DM Mono', monospace;
  letter-spacing: .22em; text-transform: uppercase;
}
.nx-hero {
  position: relative; overflow: hidden;
  padding: 30px 32px 28px; margin: 4px 0 24px;
  border: 1px solid rgba(113, 178, 204, .22);
  border-radius: 22px;
  background:
    radial-gradient(circle at 86% 20%, rgba(101, 123, 255, .23), transparent 27%),
    radial-gradient(circle at 68% 100%, rgba(48, 205, 184, .13), transparent 34%),
    linear-gradient(120deg, rgba(17, 37, 54, .96), rgba(12, 20, 36, .94));
  box-shadow: 0 22px 70px rgba(0,0,0,.25), inset 0 1px rgba(255,255,255,.04);
}
.nx-hero:after {
  content: '◈'; position: absolute; right: 5%; top: 3%;
  color: rgba(103, 231, 216, .12); font-size: 150px; line-height: 1;
}
.nx-hero h1 { font-size: clamp(2rem, 4vw, 3.35rem); margin: 9px 0 5px; }
.nx-hero p { color: #9eb2c8; margin: 0; max-width: 660px; }
.nx-pill {
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid rgba(77,229,208,.3); border-radius: 99px;
  padding: 6px 11px; color: #9bf5e8; background: rgba(37,177,164,.09);
  font: 500 .68rem 'DM Mono', monospace; letter-spacing: .1em;
}
.nx-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 12px var(--cyan); }
.nx-section {
  display:flex; justify-content:space-between; align-items:center;
  gap: 12px; margin: 26px 0 12px;
}
.nx-section small { color: var(--cyan); font: 500 .68rem 'DM Mono', monospace; letter-spacing: .16em; }
.nx-section h3 { margin: 3px 0 0; }
.nx-panel {
  background: linear-gradient(145deg, rgba(17,29,45,.88), rgba(11,19,31,.86));
  border: 1px solid var(--line); border-radius: 17px;
  padding: 20px 22px; box-shadow: 0 14px 36px rgba(0,0,0,.14);
}
.nx-panel-title { color:#eaf2fb; font-weight:800; margin-bottom:4px; }
.nx-panel-sub { color:#8fa2b8; font-size:.82rem; }
.nx-foot {
  color: #64768c; font: 400 .68rem 'DM Mono', monospace;
  letter-spacing: .08em; text-align:center; padding: 24px 0 4px;
}
</style>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
def run_tool(args, timeout=900):
    try:
        result = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
        return result.returncode, output.strip()
    except subprocess.TimeoutExpired:
        return 124, "The command exceeded the dashboard time limit. Try a smaller scan or try again later."
    except Exception as exc:
        return 1, str(exc)


def load_watchlist():
    if not WATCHLIST.exists():
        return None
    try:
        return json.loads(WATCHLIST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ensure_universe():
    if (TRADER / "universe.txt").exists():
        return 0, "Existing universe file found."
    TRADER.mkdir(exist_ok=True)
    return run_tool(["trader-scanner/scan.py", "universe"], timeout=180)


def valid_ticker(value):
    return bool(value) and value.replace(".", "").replace("-", "").isalnum()


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown('<div class="nx-brand">NEXUS<span> /</span> TRADE</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="nx-pill"><span class="nx-dot"></span> PAPER MODE ACTIVE</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**WORKSPACE**")
    st.caption("Market intelligence terminal")
    st.markdown("---")
    st.markdown("**DATA NETWORK**")
    st.caption("Yahoo Finance")
    st.caption("Nasdaq Trader")
    st.markdown("---")
    st.caption("No broker connection")
    st.caption("No live orders")
    st.caption("On-demand research only")
    st.markdown("---")
    st.caption("NEXUS TERMINAL · v1.0")


# ---------- Hero ----------
st.markdown("""
<div class="nx-hero">
  <div class="nx-kicker">MARKET INTELLIGENCE SYSTEM / 01</div>
  <h1>NEXUS <span style="color:#4de5d0">TERMINAL</span></h1>
  <p>A focused command center for discovering technical setups, tracking market catalysts and reviewing entry conditions.</p>
  <div style="margin-top:20px"><span class="nx-pill"><span class="nx-dot"></span> RESEARCH ENVIRONMENT · LIVE ORDERS DISABLED</span></div>
</div>
""", unsafe_allow_html=True)

tab_scan, tab_news, tab_entry, tab_about = st.tabs(
    ["◈  MARKET SCANNER", "⌁  NEWS RADAR", "⌖  ENTRY LAB", "ⓘ  SYSTEM"]
)

# ---------- Scanner ----------
with tab_scan:
    st.markdown("""
    <div class="nx-section">
      <div><small>MODULE 01 / DISCOVERY</small><h3>Daily market scan</h3></div>
      <span class="nx-pill">DAILY TIMEFRAME</span>
    </div>
    """, unsafe_allow_html=True)
    st.caption("Technical pattern discovery across US-listed stocks. A match is a research candidate, never an automatic buy signal.")

    left, right = st.columns([2.2, 1])
    with left:
        limit = st.slider("Universe scan depth", min_value=100, max_value=5942, value=5942, step=100)
    with right:
        st.markdown('<div class="nx-panel"><div class="nx-panel-title">SCAN CONFIGURATION</div><div class="nx-panel-sub">Daily candles · Liquidity filtered · Yahoo Finance</div></div>', unsafe_allow_html=True)

    if st.button("▶  INITIALIZE DAILY SCAN", type="primary", use_container_width=True):
        with st.spinner("Initializing market data pipeline and scanning charts..."):
            code, message = ensure_universe()
            if code == 0:
                code, message = run_tool(
                    ["trader-scanner/scan.py", "daily", "--limit", str(limit)],
                    timeout=1200,
                )
        if code == 0:
            st.session_state["scan_status"] = "Scan completed successfully."
            st.session_state.pop("scan_error", None)
        else:
            st.session_state["scan_error"] = message or "The scanner returned an error."
            st.session_state.pop("scan_status", None)

    if st.session_state.get("scan_status"):
        st.success(st.session_state["scan_status"])
    if st.session_state.get("scan_error"):
        st.error("The scan did not complete successfully.")
        with st.expander("Open diagnostic report"):
            st.code(st.session_state["scan_error"], language="text")

    doc = load_watchlist()
    if doc:
        hits = doc.get("hits", [])
        st.markdown('<div class="nx-section"><div><small>MARKET SNAPSHOT</small><h3>Scan intelligence</h3></div></div>', unsafe_allow_html=True)
        a, b, c, d = st.columns(4)
        a.metric("Universe", f'{doc.get("universe", 0):,}')
        b.metric("Charts analyzed", f'{doc.get("scanned", 0):,}')
        c.metric("Pattern matches", f'{len(hits):,}')
        d.metric("Data through", str(doc.get("as_of") or "Unknown"))
        st.caption(f"Source: {doc.get('source', 'Unknown')}  ·  Mode: {doc.get('mode', 'daily')}  ·  {doc.get('note', '')}")

        if hits:
            import pandas as pd

            rows = []
            for hit in hits:
                rows.append({
                    "Ticker": hit.get("symbol", ""),
                    "Price": hit.get("price"),
                    "RSI": hit.get("rsi"),
                    "Volume": hit.get("volume"),
                    "Setup": ", ".join(hit.get("setups", [])),
                })
            frame = pd.DataFrame(rows)
            f1, f2 = st.columns([1.5, 1])
            with f1:
                search_symbol = st.text_input("Filter by ticker", placeholder="Search symbols, e.g. NVDA")
            with f2:
                setup_values = sorted({s for hit in hits for s in hit.get("setups", [])})
                setup_filter = st.selectbox("Pattern filter", ["All patterns"] + setup_values)
            if search_symbol:
                frame = frame[frame["Ticker"].str.contains(search_symbol.strip(), case=False, na=False)]
            if setup_filter != "All patterns":
                frame = frame[frame["Setup"].str.contains(setup_filter, case=False, na=False)]
            st.dataframe(
                frame,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Price": st.column_config.NumberColumn(format="$%.2f"),
                    "RSI": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
                    "Volume": st.column_config.NumberColumn(format="localized"),
                },
            )
            st.download_button(
                "↓  EXPORT WATCHLIST CSV",
                data=frame.to_csv(index=False).encode("utf-8"),
                file_name="nexus-market-watchlist.csv",
                mime="text/csv",
            )
        else:
            st.info("No pattern matches in the current saved watchlist.")
    else:
        st.markdown('<div class="nx-panel"><div class="nx-panel-title">Awaiting first dataset</div><div class="nx-panel-sub">Initialize a daily scan to populate the market intelligence table.</div></div>', unsafe_allow_html=True)

# ---------- News ----------
with tab_news:
    st.markdown('<div class="nx-section"><div><small>MODULE 02 / CATALYSTS</small><h3>News radar</h3></div><span class="nx-pill">HEADLINE MONITOR</span></div>', unsafe_allow_html=True)
    st.caption("Retrieve recent headlines for an individual ticker. Headlines can be incomplete or delayed.")
    n1, n2 = st.columns([1.5, 1])
    with n1:
        ticker_news = st.text_input("Ticker symbol", value="INTC", max_chars=10).strip().upper()
    with n2:
        hours = st.select_slider("Lookback window", options=[6, 12, 24, 48, 72], value=24)
    if st.button("⌁  SCAN NEWS FEED", use_container_width=True):
        if not valid_ticker(ticker_news):
            st.warning("Enter a valid ticker symbol.")
        else:
            with st.spinner(f"Scanning news sources for {ticker_news}..."):
                code, message = run_tool([
                    "trader-news/news.py", "--tickers", ticker_news,
                    "--hours", str(hours), "--no-sec"
                ], timeout=120)
            st.markdown('<div class="nx-panel">', unsafe_allow_html=True)
            st.code(message or "No headlines returned.", language="text")
            st.markdown('</div>', unsafe_allow_html=True)
            if code not in (0, 1):
                st.warning("The news command returned an error. Review the diagnostic output.")

# ---------- Entry lab ----------
with tab_entry:
    st.markdown('<div class="nx-section"><div><small>MODULE 03 / VALIDATION</small><h3>Entry lab</h3></div><span class="nx-pill">NO ORDER EXECUTION</span></div>', unsafe_allow_html=True)
    st.caption("Review the tool's default opening-range-breakout entry conditions for a ticker. This is an analysis only.")
    ticker_entry = st.text_input("Asset ticker", value="INTC", max_chars=10).strip().upper()
    if st.button("⌖  RUN ENTRY DIAGNOSTIC", use_container_width=True):
        if not valid_ticker(ticker_entry):
            st.warning("Enter a valid ticker symbol.")
        else:
            with st.spinner(f"Evaluating entry conditions for {ticker_entry}..."):
                code, message = run_tool([
                    "trader-entry/entry.py", "check", ticker_entry, "--json"
                ], timeout=120)
            st.code(message or "No diagnostic output.", language="json")
            if code not in (0, 1):
                st.warning("The entry check returned an error. Review the output above.")

# ---------- System ----------
with tab_about:
    st.markdown('<div class="nx-section"><div><small>MODULE 04 / TRANSPARENCY</small><h3>System status & safeguards</h3></div></div>', unsafe_allow_html=True)
    x, y = st.columns(2)
    with x:
        st.markdown("""
        <div class="nx-panel">
          <div class="nx-panel-title">CONNECTED DATA SOURCES</div>
          <p class="nx-panel-sub">◈ Yahoo Finance public market data</p>
          <p class="nx-panel-sub">◈ Nasdaq Trader symbol directory</p>
          <p class="nx-panel-sub">◈ On-demand ticker news feed</p>
        </div>
        """, unsafe_allow_html=True)
    with y:
        st.markdown("""
        <div class="nx-panel">
          <div class="nx-panel-title">EXECUTION SAFETY</div>
          <p class="nx-panel-sub">● Paper / research mode only</p>
          <p class="nx-panel-sub">● No broker account connected</p>
          <p class="nx-panel-sub">● No live orders or trade execution</p>
        </div>
        """, unsafe_allow_html=True)
    st.warning(
        "Free public data may be delayed, rate-limited, adjusted, incomplete or incorrect. "
        "Technical matches are not recommendations and are not guaranteed to be profitable."
    )
    st.info("This dashboard is a research interface for the MIT-licensed day-trader-skill project. Live trading is not implemented. Never add broker API keys or credentials to this public repository.")

st.markdown('<div class="nx-foot">NEXUS TERMINAL · MARKET INTELLIGENCE · PAPER / RESEARCH ONLY</div>', unsafe_allow_html=True)
