import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
TRADER = ROOT / "trader"
WATCHLIST = TRADER / "watchlist.json"

st.set_page_config(page_title="Day Trader Dashboard", page_icon="📈", layout="wide")
st.title("📈 Day Trader Dashboard")
st.caption("Research and paper-trading workspace powered by the day-trader-skill tools.")

st.sidebar.success("PAPER / RESEARCH MODE")
st.sidebar.caption("No broker connection. No live orders. Scans and news are on-demand.")
st.sidebar.markdown("**Data source**")
st.sidebar.caption("Yahoo Finance and Nasdaq Trader public endpoints. Data can be delayed, incomplete, or incorrect.")

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

tab_scan, tab_news, tab_entry, tab_about = st.tabs(
    ["Stock scanner", "News", "Entry check", "About & safety"]
)

with tab_scan:
    st.subheader("Daily stock scanner")
    st.write("Finds daily-chart setups across US-listed stocks. These are research candidates, not buy signals.")
    limit = st.slider("Maximum stocks to scan", min_value=100, max_value=5942, value=5942, step=100)
    if st.button("Run daily scan", type="primary", use_container_width=True):
        with st.spinner("Preparing the stock universe and scanning charts. This can take several minutes..."):
            code, message = ensure_universe()
            if code == 0:
                code, message = run_tool([
                    "trader-scanner/scan.py", "daily",
                    "--limit", str(limit), "--json", "--show", "25"
                ], timeout=1200)
        if code in (0, 1):
            st.session_state["scan_message"] = message
            st.session_state["scan_code"] = code
        else:
            st.error(message)
    if "scan_message" in st.session_state:
        st.code(st.session_state["scan_message"], language="text")
    doc = load_watchlist()
    if doc:
        hits = doc.get("hits", [])
        a, b, c, d = st.columns(4)
        a.metric("Stocks in universe", f'{doc.get("universe", 0):,}')
        b.metric("Charts scanned", f'{doc.get("scanned", 0):,}')
        c.metric("Matching setups", f'{len(hits):,}')
        d.metric("Data through", str(doc.get("as_of") or "Unknown"))
        st.caption(doc.get("note", ""))
        if hits:
            import pandas as pd
            rows = []
            for hit in hits:
                rows.append({
                    "Ticker": hit.get("symbol", ""),
                    "Name": hit.get("name", ""),
                    "Price": hit.get("price"),
                    "RSI": hit.get("rsi"),
                    "Setups": ", ".join(hit.get("setups", [])),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No matching setups in the saved watchlist yet.")
    else:
        st.info("No saved watchlist yet. Run the daily scan to populate it.")

with tab_news:
    st.subheader("Stock news")
    ticker_news = st.text_input("Ticker", value="INTC", max_chars=10).strip().upper()
    hours = st.select_slider("Look back", options=[6, 12, 24, 48, 72], value=24)
    if st.button("Fetch news", use_container_width=True):
        if not ticker_news or not ticker_news.replace(".", "").isalnum():
            st.warning("Enter a valid ticker symbol.")
        else:
            with st.spinner(f"Fetching headlines for {ticker_news}..."):
                code, message = run_tool([
                    "trader-news/news.py", "--tickers", ticker_news,
                    "--hours", str(hours), "--no-sec"
                ], timeout=120)
            st.code(message or "No output.", language="text")
            if code not in (0, 1):
                st.warning("The news command returned an error. Check the output above.")

with tab_entry:
    st.subheader("Entry setup check")
    ticker_entry = st.text_input("Stock ticker to check", value="INTC", max_chars=10).strip().upper()
    st.caption("Checks the tool's default opening-range-breakout setup. It does not place an order.")
    if st.button("Check entry conditions", use_container_width=True):
        if not ticker_entry or not ticker_entry.replace(".", "").isalnum():
            st.warning("Enter a valid ticker symbol.")
        else:
            with st.spinner(f"Checking {ticker_entry}..."):
                code, message = run_tool([
                    "trader-entry/entry.py", "check", ticker_entry, "--json"
                ], timeout=120)
            st.code(message or "No output.", language="text")
            if code not in (0, 1):
                st.warning("The entry check returned an error. Check the output above.")

with tab_about:
    st.subheader("What this dashboard does")
    st.markdown(
        "- Runs the repository's existing daily stock scanner.\n"
        "- Displays the saved watchlist and scan metadata.\n"
        "- Fetches ticker-specific headlines on demand.\n"
        "- Checks opening-range entry conditions on demand.\n"
        "- Keeps all actions in research mode; no broker orders are sent."
    )
    st.warning(
        "Market data is supplied by free, unofficial endpoints and may be delayed, "
        "rate-limited, adjusted, or wrong. The dashboard is not investment advice. "
        "Signals are not guaranteed to be profitable."
    )
    st.error(
        "Live trading is not implemented in this dashboard. Do not add broker API "
        "keys or credentials to this public repository."
    )

st.divider()
st.caption("Day Trader Dashboard • Built on the MIT-licensed day-trader-skill project • Paper/research only")
