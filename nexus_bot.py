"""NEXUS paper-only intraday ORB engine.

This module is deliberately locked to Alpaca's paper trading endpoint.
It never accepts a live endpoint or live-trading mode.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PAPER_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"
ET = ZoneInfo("America/New_York")
BASE_CAPITAL = 100.0
RISK_FRACTION = 0.01
RISK_DOLLARS = BASE_CAPITAL * RISK_FRACTION
MAX_POSITION_VALUE = 100.0
MAX_DAILY_LOSS = 2.0
MAX_TRADES_PER_DAY = 2
MAX_ENTRIES_LAST_7D = 3  # conservative guard for Alpaca paper PDT simulation
MAX_OPEN_POSITIONS = 1
ENTRY_CUTOFF = (15, 30)
FLATTEN_TIME = (15, 55)
ORB_MINUTES = 15
TARGET_R = 2.0
BOT_PREFIX = "nexus-orb-"


class BotError(RuntimeError):
    pass


class AlpacaPaperClient:
    def __init__(self, key, secret, timeout=20):
        if not key or not secret:
            raise BotError("Missing Alpaca paper API credentials.")
        self.key = key
        self.secret = secret
        self.timeout = timeout

    def request(self, method, path, body=None, data=False):
        base = DATA_URL if data else PAPER_URL
        url = base + path
        headers = {
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
            "Accept": "application/json",
        }
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BotError("Alpaca API %s %s returned %s: %s" %
                           (method, path, exc.code, detail[:700]))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BotError("Could not reach Alpaca: %s" % exc)
        except json.JSONDecodeError:
            raise BotError("Alpaca returned an unreadable response.")

    def account(self):
        return self.request("GET", "/v2/account")

    def clock(self):
        return self.request("GET", "/v2/clock")

    def positions(self):
        return self.request("GET", "/v2/positions")

    def orders(self, after=None):
        query = {"status": "all", "limit": 500, "direction": "desc", "nested": "true"}
        if after:
            query["after"] = after
        return self.request("GET", "/v2/orders?" + urllib.parse.urlencode(query))

    def bars(self, symbol, start, end):
        query = urllib.parse.urlencode({
            "timeframe": "5Min",
            "start": start,
            "end": end,
            "limit": 10000,
            "feed": "iex",
            "adjustment": "raw",
        })
        result = self.request(
            "GET", "/v2/stocks/%s/bars?%s" % (urllib.parse.quote(symbol), query), data=True
        )
        return result.get("bars", [])

    def submit_bracket(self, symbol, qty, entry_limit, stop, target, client_order_id):
        # Whole-share limit-entry bracket orders only. Fractional bracket support is not assumed.
        # The entry limit prevents the bot paying above the price used for risk sizing.
        body = {
            "symbol": symbol,
            "qty": str(int(qty)),
            "side": "buy",
            "type": "limit",
            "limit_price": "%.2f" % entry_limit,
            "time_in_force": "day",
            "order_class": "bracket",
            "take_profit": {"limit_price": "%.2f" % target},
            "stop_loss": {"stop_price": "%.2f" % stop},
            "client_order_id": client_order_id,
        }
        return self.request("POST", "/v2/orders", body=body)

    def cancel_order(self, order_id):
        return self.request("DELETE", "/v2/orders/" + urllib.parse.quote(order_id))

    def close_position(self, symbol):
        return self.request("DELETE", "/v2/positions/" + urllib.parse.quote(symbol))


def as_et(timestamp):
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ET)


def round_price(value):
    return round(float(value) + 1e-9, 2)


def orb_signal(bars, now):
    """Return the first confirmed long 15-minute ORB breakout for today's session."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    now = now.astimezone(ET)
    today = now.date()
    session = []
    for bar in bars:
        stamp = as_et(bar["t"])
        # Ignore a still-forming five-minute candle.
        if stamp.date() == today and stamp.hour >= 9 and stamp.hour < 16 and stamp + timedelta(minutes=5) <= now:
            session.append((stamp, bar))
    session.sort(key=lambda item: item[0])
    opening = [(stamp, bar) for stamp, bar in session
               if (stamp.hour, stamp.minute) in ((9, 30), (9, 35), (9, 40))]
    if len(opening) != 3:
        return None
    opening.sort(key=lambda item: item[0])
    if [(x[0].hour, x[0].minute) for x in opening] != [(9, 30), (9, 35), (9, 40)]:
        return None
    or_high = max(float(x[1]["h"]) for x in opening)
    or_low = min(float(x[1]["l"]) for x in opening)
    midpoint = (or_high + or_low) / 2.0
    for stamp, bar in session:
        if (stamp.hour, stamp.minute) < (9, 45):
            continue
        close = float(bar["c"])
        if close > or_high and close > midpoint:
            # Avoid chasing a breakout that has already extended too far.
            if close > or_high * 1.01:
                return None
            risk_per_share = close - midpoint
            if risk_per_share <= 0:
                return None
            return {
                "entry": close,
                "stop": midpoint,
                "target": close + TARGET_R * risk_per_share,
                "risk_per_share": risk_per_share,
                "signal_time": stamp.isoformat(),
                "or_high": or_high,
                "or_low": or_low,
            }
    return None


def size_position(entry, stop, capital=BASE_CAPITAL, risk_fraction=RISK_FRACTION):
    """Whole-share sizing: never exceed either the dollar-risk or notional cap."""
    risk_per_share = float(entry) - float(stop)
    if risk_per_share <= 0 or entry <= 0:
        return 0, 0.0
    risk_budget = float(capital) * float(risk_fraction)
    by_risk = math.floor(risk_budget / risk_per_share)
    by_cash = math.floor(min(float(capital), MAX_POSITION_VALUE) / float(entry))
    qty = max(0, min(by_risk, by_cash))
    return qty, round(qty * risk_per_share, 2)


def backtest_orb(bars, capital=BASE_CAPITAL):
    """Conservative daily ORB replay; stop wins if stop and target touch in one bar."""
    sessions = {}
    for bar in bars:
        stamp = as_et(bar["t"])
        sessions.setdefault(stamp.date(), []).append((stamp, bar))
    trades = []
    equity = float(capital)
    for day in sorted(sessions):
        rows = sorted(sessions[day], key=lambda x: x[0])
        opening = [(t, b) for t, b in rows if (t.hour, t.minute) in ((9, 30), (9, 35), (9, 40))]
        if len(opening) != 3:
            continue
        opening.sort(key=lambda x: x[0])
        if [(x[0].hour, x[0].minute) for x in opening] != [(9, 30), (9, 35), (9, 40)]:
            continue
        hi = max(float(x[1]["h"]) for x in opening)
        lo = min(float(x[1]["l"]) for x in opening)
        stop = (hi + lo) / 2
        trigger = None
        session_flatten = min(
            datetime.combine(day, datetime.min.time(), tzinfo=ET).replace(hour=15, minute=55),
            rows[-1][0],
        )
        session_entry_cutoff = session_flatten - timedelta(minutes=25)
        for t, bar in rows:
            if t < datetime.combine(day, datetime.min.time(), tzinfo=ET).replace(hour=9, minute=45) or t > session_entry_cutoff:
                continue
            close = float(bar["c"])
            if close > hi and close <= hi * 1.01:
                trigger = (t, bar, close)
                break
        if trigger is None:
            continue
        entry_time, entry_bar, entry = trigger
        qty, planned_risk = size_position(entry, stop, capital=equity)
        if qty < 1:
            continue
        target = entry + TARGET_R * (entry - stop)
        exit_price, exit_reason = float(rows[-1][1]["c"]), "close"
        for t, bar in rows:
            if t <= entry_time:
                continue
            low, high = float(bar["l"]), float(bar["h"])
            if low <= stop:
                exit_price, exit_reason = stop, "stop"
                break
            if high >= target:
                exit_price, exit_reason = target, "target"
                break
            if (t.hour, t.minute) >= FLATTEN_TIME:
                exit_price, exit_reason = float(bar["c"]), "time"
                break
        # Include a conservative 5 bp per side slippage estimate in the replay.
        pnl = (exit_price * 0.9995 - entry * 1.0005) * qty
        equity += pnl
        trades.append({
            "date": day.isoformat(),
            "entry_time": entry_time.strftime("%H:%M"),
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "qty": qty,
            "planned_risk": planned_risk,
            "exit": round(exit_price, 2),
            "exit_reason": exit_reason,
            "pnl": round(pnl, 2),
            "equity": round(equity, 2),
        })
    wins = sum(1 for trade in trades if trade["pnl"] > 0)
    losses = sum(1 for trade in trades if trade["pnl"] <= 0)
    return {
        "trades": trades,
        "trade_count": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(100 * wins / len(trades), 1) if trades else 0.0,
        "net_pnl": round(equity - capital, 2),
        "ending_equity": round(equity, 2),
        "note": "Historical replay only; stop-first same-bar assumption and estimated slippage. Not a prediction.",
    }


def _daily_order_stats(orders, today):
    prefix = BOT_PREFIX + today.replace("-", "") + "-"
    parents = [o for o in orders if str(o.get("client_order_id", "")).startswith(prefix)]
    realized = 0.0
    for parent in parents:
        legs = parent.get("legs") or []
        entry = float(parent.get("filled_avg_price") or 0)
        for leg in legs:
            if leg.get("side") == "sell" and leg.get("status") == "filled" and entry > 0:
                qty = float(leg.get("filled_qty") or 0)
                exit_price = float(leg.get("filled_avg_price") or 0)
                realized += (exit_price - entry) * qty
    return len(parents), realized, parents


def _recent_entry_count(orders):
    # Count filled NEXUS entry parents over the last seven calendar days.
    # This is deliberately conservative: it counts entries even if they were not
    # closed intraday, rather than risking a fourth simulated day trade.
    return sum(
        1 for order in orders
        if str(order.get("client_order_id", "")).startswith(BOT_PREFIX)
        and float(order.get("filled_qty") or 0) > 0
    )


def flatten_bot_positions(client, positions, parents):
    """Close only NEXUS-owned positions and cancel their remaining bracket legs."""
    owned = {o.get("symbol"): o for o in parents
             if str(o.get("client_order_id", "")).startswith(BOT_PREFIX)}
    closed = []
    for position in positions:
        symbol = position.get("symbol")
        if symbol not in owned:
            continue
        parent = owned[symbol]
        for leg in parent.get("legs") or []:
            if leg.get("status") not in ("filled", "canceled", "expired", "rejected"):
                try:
                    client.cancel_order(leg["id"])
                except BotError:
                    pass
        client.close_position(symbol)
        closed.append(symbol)
    return closed


def run_cycle(client, symbols, now=None):
    """Run exactly one paper-only decision cycle and at most one new entry."""
    now = now or datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    now = now.astimezone(ET)
    if now.weekday() >= 5:
        return {"status": "idle", "message": "US stock market is closed for the weekend."}

    account = client.account()
    if account.get("status") != "ACTIVE" or account.get("trading_blocked"):
        return {"status": "blocked", "message": "Alpaca account is not active or trading is blocked."}
    equity = float(account.get("equity") or 0)
    if equity > 110 or equity < 90:
        return {"status": "blocked", "message": (
            "Alpaca paper account equity is $%.2f. This bot is configured for a $100 paper account "
            "and will only run when equity is between $90 and $110. Create/reset a paper account "
            "with $100 starting balance first." % equity
        )}

    clock = client.clock()
    if not clock.get("is_open"):
        return {"status": "idle", "message": "NYSE session is currently closed."}

    # Use five minutes before the actual session close, including half-days.
    next_close = as_et(clock["next_close"]) if clock.get("next_close") else now.replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    regular_flatten = now.replace(hour=FLATTEN_TIME[0], minute=FLATTEN_TIME[1], second=0, microsecond=0)
    flatten_at = min(regular_flatten, next_close - timedelta(minutes=5))
    entry_cutoff = min(
        now.replace(hour=ENTRY_CUTOFF[0], minute=ENTRY_CUTOFF[1], second=0, microsecond=0),
        flatten_at - timedelta(minutes=25),
    )

    today = now.strftime("%Y-%m-%d")
    start_utc = datetime.combine(now.date(), datetime.min.time(), tzinfo=ET).astimezone(timezone.utc)
    orders = client.orders(after=start_utc.isoformat().replace("+00:00", "Z"))
    trade_count, realized, parents = _daily_order_stats(orders, today)
    week_start = (now - timedelta(days=7)).astimezone(timezone.utc)
    recent_orders = client.orders(after=week_start.isoformat().replace("+00:00", "Z"))
    recent_entries = _recent_entry_count(recent_orders)
    positions = client.positions()

    if now >= flatten_at:
        flattened = flatten_bot_positions(client, positions, parents)
        return {"status": "flattened" if flattened else "idle",
                "symbols": flattened,
                "message": ("Closed NEXUS positions for the intraday cutoff." if flattened
                            else "Intraday cutoff reached; no NEXUS-owned open positions found.")}

    if (now.hour, now.minute) < (9, 45):
        return {"status": "idle", "message": "Waiting for the 15-minute opening range to complete (9:45 AM ET)."}

    day_change = equity - float(account.get("last_equity") or equity)
    if day_change <= -MAX_DAILY_LOSS or realized <= -MAX_DAILY_LOSS:
        return {"status": "blocked", "message": "Daily loss guard reached (limit: $%.2f). No more entries today." % MAX_DAILY_LOSS}
    if trade_count >= MAX_TRADES_PER_DAY:
        return {"status": "blocked", "message": "Daily trade limit reached (%d)." % MAX_TRADES_PER_DAY}
    if recent_entries >= MAX_ENTRIES_LAST_7D:
        return {"status": "blocked", "message": "Conservative 7-day day-trade guard reached (%d entries). Wait until an entry rolls out of the lookback window." % MAX_ENTRIES_LAST_7D}

    if positions:
        return {"status": "idle", "message": "An open position already exists. NEXUS allows only one position at a time."}

    if now > entry_cutoff:
        return {"status": "idle", "message": "Entry cutoff passed; no new trade is opened within 25 minutes of the session close."}

    for symbol in list(dict.fromkeys(s.upper() for s in symbols if s))[:25]:
        client_id = BOT_PREFIX + now.strftime("%Y%m%d") + "-" + symbol
        if any(o.get("client_order_id") == client_id for o in parents):
            continue
        bars = client.bars(symbol, start_utc.isoformat().replace("+00:00", "Z"),
                           now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
        signal = orb_signal(bars, now)
        if not signal:
            continue
        # Add one cent of limit-price tolerance, then size against that exact cap.
        entry_limit = round_price(signal["entry"] + 0.01)
        stop_price = round_price(signal["stop"])
        qty, planned_risk = size_position(entry_limit, stop_price)
        if qty < 1:
            continue
        if planned_risk > RISK_DOLLARS + 0.01:
            continue
        target_price = round_price(entry_limit + TARGET_R * (entry_limit - stop_price))
        order = client.submit_bracket(
            symbol, qty, entry_limit, stop_price, target_price, client_id
        )
        return {
            "status": "submitted",
            "symbol": symbol,
            "qty": qty,
            "entry_limit": entry_limit,
            "stop": stop_price,
            "target": target_price,
            "planned_max_loss": planned_risk,
            "order_id": order.get("id"),
            "message": "Paper bracket order submitted. Check Alpaca for fill status; actual loss can exceed planned risk during gaps or slippage.",
        }
    return {"status": "no_signal", "message": "No qualifying 15-minute opening-range breakout found in the selected symbols."}


def load_symbols():
    path = Path("trader/watchlist.json")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return [x.get("symbol", "") for x in doc.get("hits", [])[:25] if x.get("symbol")]
    except (OSError, ValueError, TypeError):
        return ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]


def main():
    parser = argparse.ArgumentParser(description="NEXUS Alpaca paper-only intraday ORB bot.")
    parser.add_argument("--loop", action="store_true", help="repeat paper decision cycles while this process stays running")
    parser.add_argument("--interval", type=int, default=60, help="seconds between cycles (minimum 30)")
    args = parser.parse_args()
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    client = AlpacaPaperClient(key, secret)
    symbols = load_symbols()
    if args.loop:
        interval = max(30, args.interval)
        print("NEXUS PAPER BOT running. Stop with Ctrl+C. Paper endpoint is hard-coded.")
        try:
            while True:
                try:
                    print(json.dumps(run_cycle(client, symbols), indent=2))
                except BotError as exc:
                    print("BOT ERROR:", exc, file=sys.stderr)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("NEXUS paper bot stopped.")
    else:
        print(json.dumps(run_cycle(client, symbols), indent=2))


if __name__ == "__main__":
    main()
