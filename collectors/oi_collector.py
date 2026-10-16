"""
Intraday OI + Option Chain Collector — collects OI + full chain for 37 symbols.

Runs every 15 min (9:20 to 15:29) + CAS closing price at 15:42.
Each snapshot collects:
  1. OI summary (ATM data, PCR, max OI strikes) -> data/oi_snapshots/
  2. Full option chain (all strikes x CE/PE: OI, IV, Greeks, bid/ask) -> data/option_chain/
15:29 snapshot captures last continuous price before CAS auction (15:30-15:40).

Usage:
    python -m collectors.oi_collector              # single OI snapshot now
    python -m collectors.oi_collector --chain      # single chain snapshot now
    python -m collectors.oi_collector --schedule   # every 15 min 9:20-15:29 + CAS at 15:42
    python -m collectors.oi_collector --info       # show collected data summary
"""

import os
import sys
import time
import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from utils.logger import get_logger
from utils.upstox_data import _get, _BASE

log = get_logger("oi_collector")

IST = timezone(timedelta(hours=5, minutes=30))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "data", "oi_snapshots")
CHAIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         "data", "option_chain")

STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL",
    "SBIN", "ITC", "LT", "HINDUNILVR", "KOTAKBANK", "AXISBANK",
    "MARUTI", "SUNPHARMA", "TITAN", "BAJFINANCE", "WIPRO", "HCLTECH",
    "ADANIENT", "TATAMOTORS", "TATASTEEL", "POWERGRID", "NTPC", "ONGC",
    "COALINDIA", "JSWSTEEL", "DRREDDY", "BAJAJFINSV", "ASIANPAINT",
    "TECHM", "INDUSINDBK", "M&M", "CIPLA", "EICHERMOT", "SBILIFE",
]

INDICES = ["NIFTY", "BANKNIFTY"]

INDEX_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}

_key_cache: dict[str, str] = {}
_KEY_CACHE_FILE = os.path.join(DATA_DIR, "_instrument_keys.json")


def _load_key_cache():
    global _key_cache
    if os.path.isfile(_KEY_CACHE_FILE):
        with open(_KEY_CACHE_FILE, "r") as f:
            _key_cache = json.load(f)


def _save_key_cache():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_KEY_CACHE_FILE, "w") as f:
        json.dump(_key_cache, f, indent=2)


def _has_fo_contracts(instrument_key: str) -> bool:
    data = _get(f"{_BASE}/option/contract", {"instrument_key": instrument_key}, timeout=10)
    if not data:
        return False
    today = date.today()
    return any(
        date.fromisoformat(c.get("expiry", "")[:10]) >= today
        for c in data if c.get("expiry", "")
    )


def _resolve_key(symbol: str, force_refresh: bool = False) -> str | None:
    if symbol in INDEX_KEYS:
        return INDEX_KEYS[symbol]
    if symbol in _key_cache and not force_refresh:
        return _key_cache[symbol]

    data = _get(f"{_BASE}/instruments/search", {
        "query": symbol, "exchanges": "NSE", "segments": "EQ",
    }, timeout=10)
    candidates = []
    if data:
        results = data if isinstance(data, list) else []
        for r in results:
            key = r.get("instrument_key", "")
            if key and key not in candidates:
                candidates.append(key)

    for key in candidates:
        if _has_fo_contracts(key):
            _key_cache[symbol] = key
            _save_key_cache()
            return key

    if candidates:
        key = candidates[0]
        _key_cache[symbol] = key
        _save_key_cache()
        return key
    return None


def _get_nearest_expiry(instrument_key: str) -> str | None:
    data = _get(f"{_BASE}/option/contract", {"instrument_key": instrument_key}, timeout=10)
    if not data:
        return None
    today = date.today()
    expiries = set()
    for contract in data:
        exp_str = contract.get("expiry", "")
        if not exp_str:
            continue
        try:
            exp_date = date.fromisoformat(exp_str[:10])
            if exp_date >= today:
                expiries.add(exp_str[:10])
        except ValueError:
            continue
    return sorted(expiries)[0] if expiries else None


def _load_baseline() -> dict[str, dict]:
    today_str = date.today().isoformat()
    path = os.path.join(DATA_DIR, f"oi_{today_str}.parquet")
    if not os.path.isfile(path):
        return {}
    df = pd.read_parquet(path)
    if df.empty:
        return {}
    first_ts = df["timestamp"].min()
    first = df[df["timestamp"] == first_ts]
    baseline = {}
    for _, row in first.iterrows():
        baseline[row["symbol"]] = {
            "spot": row["spot"],
            "total_ce_oi": row["total_ce_oi"],
            "total_pe_oi": row["total_pe_oi"],
            "atm_ce_ltp": row.get("atm_ce_ltp", 0),
            "atm_pe_ltp": row.get("atm_pe_ltp", 0),
        }
    return baseline


def _compute_oi_signal(premium_now: float, premium_open: float,
                       oi_now: int, oi_open: int) -> str:
    if oi_open == 0 or premium_open == 0:
        return "NEUTRAL"
    price_up = premium_now > premium_open
    oi_up = oi_now > oi_open
    if oi_up and price_up:
        return "LONG_BUILD"
    elif oi_up and not price_up:
        return "SHORT_BUILD"
    elif not oi_up and price_up:
        return "SHORT_COVER"
    elif not oi_up and not price_up:
        return "LONG_UNWIND"
    return "NEUTRAL"


def collect_snapshot() -> pd.DataFrame:
    """Collect OI snapshot for all stocks + indices."""
    now = datetime.now(IST)
    timestamp = now.isoformat()
    rows = []

    all_symbols = INDICES + STOCKS
    success = 0
    failed = []

    _load_key_cache()
    baseline = _load_baseline()

    for sym in all_symbols:
        key = _resolve_key(sym)
        if not key:
            log.warning("Could not resolve key for %s", sym)
            failed.append(sym)
            continue

        expiry = _get_nearest_expiry(key)
        if not expiry and sym in _key_cache:
            log.info("Retrying %s with fresh key lookup", sym)
            del _key_cache[sym]
            _save_key_cache()
            key = _resolve_key(sym, force_refresh=True)
            if key:
                expiry = _get_nearest_expiry(key)
        if not expiry:
            log.warning("No expiry found for %s", sym)
            failed.append(sym)
            continue

        oi_data = _get(f"{_BASE}/market/oi", {
            "instrument_key": key, "expiry": expiry,
            "date": date.today().isoformat(),
        }, timeout=10)

        if not oi_data:
            log.warning("OI API returned nothing for %s", sym)
            failed.append(sym)
            continue

        total_puts = int(oi_data.get("total_puts", 0) or 0)
        total_calls = int(oi_data.get("total_calls", 0) or 0)
        pcr = round(total_puts / total_calls, 4) if total_calls > 0 else 0.0
        spot = float(oi_data.get("spot_closing_price", 0) or 0)

        strike_data = oi_data.get("call_put_oi_data_list", [])
        max_ce_oi_strike = max_pe_oi_strike = 0
        max_ce_oi = max_pe_oi = 0

        for s in strike_data:
            ce_oi = int(s.get("call_oi", 0) or 0)
            pe_oi = int(s.get("put_oi", 0) or 0)
            strike = int(s.get("strike_price", 0) or 0)
            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                max_ce_oi_strike = strike
            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                max_pe_oi_strike = strike

        atm_ce_bid = atm_ce_ask = atm_ce_ltp = 0.0
        atm_pe_bid = atm_pe_ask = atm_pe_ltp = 0.0
        atm_strike = 0
        if spot > 0:
            chain_data = _get(f"{_BASE}/option/chain", {
                "instrument_key": key, "expiry_date": expiry,
            }, timeout=10)
            if chain_data:
                chain_rows = chain_data if isinstance(chain_data, list) else []
                closest = min(chain_rows,
                              key=lambda r: abs(int(r.get("strike_price", 0)) - spot),
                              default=None)
                if closest:
                    atm_strike = int(closest.get("strike_price", 0))
                    ce_md = closest.get("call_options", {}).get("market_data", {})
                    pe_md = closest.get("put_options", {}).get("market_data", {})
                    atm_ce_bid = float(ce_md.get("bid_price", 0) or 0)
                    atm_ce_ask = float(ce_md.get("ask_price", 0) or 0)
                    atm_ce_ltp = float(ce_md.get("ltp", 0) or 0)
                    atm_pe_bid = float(pe_md.get("bid_price", 0) or 0)
                    atm_pe_ask = float(pe_md.get("ask_price", 0) or 0)
                    atm_pe_ltp = float(pe_md.get("ltp", 0) or 0)

        base = baseline.get(sym, {})
        base_ce_oi = base.get("total_ce_oi", 0)
        base_pe_oi = base.get("total_pe_oi", 0)
        base_ce_ltp = base.get("atm_ce_ltp", 0)
        base_pe_ltp = base.get("atm_pe_ltp", 0)

        ce_oi_signal = _compute_oi_signal(atm_ce_ltp, base_ce_ltp, total_calls, base_ce_oi)
        pe_oi_signal = _compute_oi_signal(atm_pe_ltp, base_pe_ltp, total_puts, base_pe_oi)
        ce_oi_change_pct = round((total_calls - base_ce_oi) / base_ce_oi * 100, 2) if base_ce_oi > 0 else 0.0
        pe_oi_change_pct = round((total_puts - base_pe_oi) / base_pe_oi * 100, 2) if base_pe_oi > 0 else 0.0
        total_oi = total_calls + total_puts
        base_total_oi = base_ce_oi + base_pe_oi
        oi_change_pct = round((total_oi - base_total_oi) / base_total_oi * 100, 2) if base_total_oi > 0 else 0.0
        pcr_change = round(pcr - (base_pe_oi / base_ce_oi if base_ce_oi > 0 else 0), 4)

        rows.append({
            "timestamp": timestamp, "symbol": sym, "expiry": expiry, "spot": spot,
            "total_ce_oi": total_calls, "total_pe_oi": total_puts, "pcr": pcr,
            "max_ce_oi": max_ce_oi, "max_ce_oi_strike": max_ce_oi_strike,
            "max_pe_oi": max_pe_oi, "max_pe_oi_strike": max_pe_oi_strike,
            "num_strikes": len(strike_data), "atm_strike": atm_strike,
            "atm_ce_ltp": atm_ce_ltp, "atm_ce_bid": atm_ce_bid, "atm_ce_ask": atm_ce_ask,
            "atm_ce_spread": round(atm_ce_ask - atm_ce_bid, 2),
            "atm_pe_ltp": atm_pe_ltp, "atm_pe_bid": atm_pe_bid, "atm_pe_ask": atm_pe_ask,
            "atm_pe_spread": round(atm_pe_ask - atm_pe_bid, 2),
            "ce_oi_signal": ce_oi_signal, "pe_oi_signal": pe_oi_signal,
            "oi_change_pct": oi_change_pct,
            "ce_oi_change_pct": ce_oi_change_pct, "pe_oi_change_pct": pe_oi_change_pct,
            "pcr_change": pcr_change,
        })
        success += 1

        if success % 10 == 0:
            log.info("Progress: %d/%d collected", success, len(all_symbols))
        time.sleep(0.3)

    log.info("Snapshot complete: %d success, %d failed", success, len(failed))
    if failed:
        log.warning("Failed symbols: %s", failed)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def save_snapshot(df: pd.DataFrame):
    if df.empty:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    today_str = date.today().isoformat()
    path = os.path.join(DATA_DIR, f"oi_{today_str}.parquet")
    if os.path.isfile(path):
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_parquet(path, engine="pyarrow", index=False)
    log.info("Saved %d rows to %s", len(df), path)


def _load_continuous_close() -> dict:
    today_str = date.today().isoformat()
    path = os.path.join(DATA_DIR, f"oi_{today_str}.parquet")
    if not os.path.isfile(path):
        return {}
    df = pd.read_parquet(path)
    last_snap = df.sort_values("timestamp").groupby("symbol").last()
    return {sym: float(row["spot"]) for sym, row in last_snap.iterrows() if row["spot"] > 0}


def collect_cas_closing() -> pd.DataFrame:
    """Fetch CAS-determined closing prices at ~15:42 for all symbols."""
    now = datetime.now(IST)
    timestamp = now.isoformat()
    rows = []
    continuous = _load_continuous_close()

    _load_key_cache()
    all_symbols = INDICES + STOCKS
    success = 0

    for sym in all_symbols:
        if sym in INDEX_KEYS:
            key = INDEX_KEYS[sym]
        elif sym in _key_cache:
            key = _key_cache[sym]
        else:
            continue

        quote = _get(f"{_BASE}/market-quote/quotes", {"instrument_key": key}, timeout=10)
        if not quote:
            continue

        quote_data = quote if isinstance(quote, dict) else {}
        if not quote_data:
            if isinstance(quote, list) and quote:
                quote_data = quote[0]
            else:
                continue

        for inst_key, q in (quote_data.items() if isinstance(quote_data, dict) else [(sym, quote_data)]):
            if isinstance(q, dict):
                cas_price = float(q.get("last_price", 0) or q.get("ltp", 0) or 0)
                cont_price = continuous.get(sym, 0.0)
                divergence = round((cas_price - cont_price) / cont_price * 100, 4) if cont_price > 0 else 0.0
                rows.append({
                    "timestamp": timestamp, "symbol": sym, "snapshot_type": "CAS_CLOSE",
                    "cas_close": cas_price, "continuous_close": cont_price,
                    "cas_divergence_pct": divergence,
                })
                success += 1
                break
        time.sleep(0.2)

    log.info("CAS closing prices collected: %d/%d symbols", success, len(all_symbols))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def save_cas_closing(df: pd.DataFrame):
    if df.empty:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    today_str = date.today().isoformat()
    path = os.path.join(DATA_DIR, f"cas_{today_str}.parquet")
    df.to_parquet(path, engine="pyarrow", index=False)
    log.info("Saved CAS closing data to %s", path)


def _extract_contract_ohlc(opt_data: dict, opt_key: str, ohlc_cache: dict) -> tuple[float, float, float, float]:
    """Extract Open, High, Low, Close for an option contract."""
    md = opt_data.get("market_data", {})
    ltp = float(md.get("ltp", 0) or 0)
    close_price = float(md.get("close_price", 0) or md.get("cp", 0) or 0)

    # 1. From market_data ohlc subdict if present
    md_ohlc = md.get("ohlc")
    if md_ohlc and isinstance(md_ohlc, dict):
        open_val = float(md_ohlc.get("open", 0) or ltp)
        high_val = float(md_ohlc.get("high", 0) or max(ltp, open_val))
        low_val = float(md_ohlc.get("low", 0) or (min(ltp, open_val) if min(ltp, open_val) > 0 else ltp))
        close_val = ltp if ltp > 0 else float(md_ohlc.get("close", 0) or close_price)
        return open_val, high_val, low_val, close_val

    # 2. From ohlc_cache (fetched quotes) if present
    if opt_key:
        cached = ohlc_cache.get(opt_key) or ohlc_cache.get(opt_key.replace("|", ":"))
        if cached:
            return (
                float(cached.get("open", ltp)),
                float(cached.get("high", ltp)),
                float(cached.get("low", ltp)),
                float(cached.get("close", ltp or close_price)),
            )

    # 3. Direct fields in market_data
    open_val = float(md.get("open", 0) or md.get("open_price", 0) or ltp)
    high_val = float(md.get("high", 0) or md.get("high_price", 0) or max(ltp, open_val))
    low_val = float(md.get("low", 0) or md.get("low_price", 0) or (min(ltp, open_val) if min(ltp, open_val) > 0 else ltp))
    close_val = ltp if ltp > 0 else close_price

    return open_val, high_val, low_val, close_val


def collect_chain_snapshot() -> pd.DataFrame:
    """Collect full option chain for all symbols.

    Saves normalized per-contract records:
    Timestamp, Symbol, Open, High, Low, Close, Volume, Open_Interest,
    Expiry_Date, Strike_Price, Option_Type, Bid_Price, Ask_Price
    (plus Spot_Price, IV, Delta, Theta, Gamma, Vega).
    """
    now = datetime.now(IST)
    timestamp = now.isoformat()
    rows = []

    all_symbols = INDICES + STOCKS
    success = 0
    failed = []

    _load_key_cache()

    for sym in all_symbols:
        key = _resolve_key(sym)
        if not key:
            failed.append(sym)
            continue

        expiry = _get_nearest_expiry(key)
        if not expiry:
            failed.append(sym)
            continue

        spot_data = _get(f"{_BASE}/market/oi", {
            "instrument_key": key, "expiry": expiry,
            "date": date.today().isoformat(),
        }, timeout=10)
        spot = float(spot_data.get("spot_closing_price", 0) or 0) if spot_data else 0.0

        chain_data = _get(f"{_BASE}/option/chain", {
            "instrument_key": key, "expiry_date": expiry,
        }, timeout=15)

        if not chain_data:
            failed.append(sym)
            time.sleep(0.3)
            continue

        chain_rows = chain_data if isinstance(chain_data, list) else []

        # Collect option contract keys to fetch OHLC quotes if not directly in market_data
        contract_keys = []
        for strike_row in chain_rows:
            ce_k = strike_row.get("call_options", {}).get("instrument_key", "")
            pe_k = strike_row.get("put_options", {}).get("instrument_key", "")
            if ce_k:
                contract_keys.append(ce_k)
            if pe_k:
                contract_keys.append(pe_k)

        ohlc_cache = {}
        sample_md = chain_rows[0].get("call_options", {}).get("market_data", {}) if chain_rows else {}
        if "ohlc" not in sample_md and contract_keys:
            try:
                from utils.upstox_data import fetch_option_quotes_ohlc
                ohlc_cache = fetch_option_quotes_ohlc(contract_keys)
            except Exception as e:
                log.debug("OHLC quotes fetch skipped for %s: %s", sym, e)

        for strike_row in chain_rows:
            raw_strike = strike_row.get("strike_price", 0)
            try:
                strike = int(raw_strike)
            except (ValueError, TypeError):
                try:
                    strike = float(raw_strike)
                except (ValueError, TypeError):
                    continue
            if strike == 0:
                continue

            ce = strike_row.get("call_options", {})
            pe = strike_row.get("put_options", {})
            ce_md = ce.get("market_data", {})
            pe_md = pe.get("market_data", {})
            ce_greeks = ce.get("option_greeks", {})
            pe_greeks = pe.get("option_greeks", {})
            ce_key = ce.get("instrument_key", "")
            pe_key = pe.get("instrument_key", "")

            if ce and (ce_key or ce_md.get("oi") or ce_md.get("ltp") or strike > 0):
                ce_o, ce_h, ce_l, ce_c = _extract_contract_ohlc(ce, ce_key, ohlc_cache)
                rows.append({
                    "Timestamp": timestamp,
                    "Symbol": sym,
                    "Open": round(ce_o, 2),
                    "High": round(ce_h, 2),
                    "Low": round(ce_l, 2),
                    "Close": round(ce_c, 2),
                    "Volume": int(ce_md.get("volume", 0) or 0),
                    "Open_Interest": int(ce_md.get("oi", 0) or 0),
                    "Expiry_Date": expiry,
                    "Strike_Price": strike,
                    "Option_Type": "CE",
                    "Bid_Price": round(float(ce_md.get("bid_price", 0) or 0), 2),
                    "Ask_Price": round(float(ce_md.get("ask_price", 0) or 0), 2),
                    "Spot_Price": spot,
                    "IV": round(float(ce_greeks.get("iv", 0) or 0), 4),
                    "Delta": round(float(ce_greeks.get("delta", 0) or 0), 4),
                    "Theta": round(float(ce_greeks.get("theta", 0) or 0), 4),
                    "Gamma": round(float(ce_greeks.get("gamma", 0) or 0), 6),
                    "Vega": round(float(ce_greeks.get("vega", 0) or 0), 4),
                })

            if pe and (pe_key or pe_md.get("oi") or pe_md.get("ltp") or strike > 0):
                pe_o, pe_h, pe_l, pe_c = _extract_contract_ohlc(pe, pe_key, ohlc_cache)
                rows.append({
                    "Timestamp": timestamp,
                    "Symbol": sym,
                    "Open": round(pe_o, 2),
                    "High": round(pe_h, 2),
                    "Low": round(pe_l, 2),
                    "Close": round(pe_c, 2),
                    "Volume": int(pe_md.get("volume", 0) or 0),
                    "Open_Interest": int(pe_md.get("oi", 0) or 0),
                    "Expiry_Date": expiry,
                    "Strike_Price": strike,
                    "Option_Type": "PE",
                    "Bid_Price": round(float(pe_md.get("bid_price", 0) or 0), 2),
                    "Ask_Price": round(float(pe_md.get("ask_price", 0) or 0), 2),
                    "Spot_Price": spot,
                    "IV": round(float(pe_greeks.get("iv", 0) or 0), 4),
                    "Delta": round(float(pe_greeks.get("delta", 0) or 0), 4),
                    "Theta": round(float(pe_greeks.get("theta", 0) or 0), 4),
                    "Gamma": round(float(pe_greeks.get("gamma", 0) or 0), 6),
                    "Vega": round(float(pe_greeks.get("vega", 0) or 0), 4),
                })

        success += 1
        if success % 10 == 0:
            log.info("Chain progress: %d/%d collected", success, len(all_symbols))
        time.sleep(0.3)

    log.info("Chain snapshot: %d success (%d option contract rows), %d failed",
             success, len(rows), len(failed))
    if failed:
        log.warning("Chain failed symbols: %s", failed)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


collect_options_data = collect_chain_snapshot


def save_chain_snapshot(df: pd.DataFrame, save_csv: bool = True):
    if df.empty:
        return
    os.makedirs(CHAIN_DIR, exist_ok=True)
    today_str = date.today().isoformat()
    path = os.path.join(CHAIN_DIR, f"chain_{today_str}.parquet")
    if os.path.isfile(path):
        existing = pd.read_parquet(path)
        df_to_save = pd.concat([existing, df], ignore_index=True)
    else:
        df_to_save = df
    df_to_save.to_parquet(path, engine="pyarrow", index=False)
    log.info("Saved %d chain rows to %s", len(df_to_save), path)

    if save_csv:
        csv_path = os.path.join(CHAIN_DIR, f"chain_{today_str}.csv")
        df_to_save.to_csv(csv_path, index=False)
        log.info("Saved %d chain rows to %s", len(df_to_save), csv_path)


save_options_data = save_chain_snapshot


def run_schedule():
    """Run every 15 min from 9:20-15:29 IST + CAS closing at 15:42."""
    from utils.market_hours import is_market_day
    if not is_market_day():
        log.info("Market holiday — skipping OI collection")
        return

    schedule_times = []
    h, m = 9, 20
    while h < 15 or (h == 15 and m <= 20):
        schedule_times.append(f"{h:02d}:{m:02d}")
        m += 15
        if m >= 60:
            h += 1
            m -= 60
    schedule_times.append("15:29")
    cas_time = "15:42"
    cas_done = False

    log.info("OI+Chain Collector: %d snapshots every 15 min (%s to %s) + CAS at %s",
             len(schedule_times), schedule_times[0], schedule_times[-1], cas_time)

    while True:
        now = datetime.now(IST)
        now_str = now.strftime("%H:%M")

        if now.hour >= 16 and cas_done:
            log.info("Market closed, stopping scheduler")
            break

        if now_str == cas_time and not cas_done:
            log.info("Collecting CAS closing prices at %s", cas_time)
            cas_df = collect_cas_closing()
            save_cas_closing(cas_df)
            cas_done = True
            time.sleep(61)
            continue

        for t in schedule_times:
            if now_str == t:
                log.info("Running scheduled snapshot at %s", t)
                df = collect_snapshot()
                save_snapshot(df)
                log.info("Running chain snapshot at %s", t)
                chain_df = collect_chain_snapshot()
                save_chain_snapshot(chain_df)
                time.sleep(61)
                break
        else:
            time.sleep(30)


def show_info():
    if os.path.isdir(DATA_DIR):
        files = sorted(f for f in os.listdir(DATA_DIR) if f.startswith("oi_") and f.endswith(".parquet"))
        if files:
            print("=== OI Snapshots ===")
            total_rows = 0
            for f in files:
                path = os.path.join(DATA_DIR, f)
                df = pd.read_parquet(path)
                total_rows += len(df)
                timestamps = df["timestamp"].nunique()
                symbols = df["symbol"].nunique()
                print(f"  {f}: {len(df)} rows, {timestamps} snapshots, {symbols} symbols")
            print(f"Total: {len(files)} days, {total_rows} rows\n")

    if os.path.isdir(CHAIN_DIR):
        files = sorted(f for f in os.listdir(CHAIN_DIR) if f.startswith("chain_") and f.endswith(".parquet"))
        if files:
            print("=== Option Chain / Options Data ===")
            total_rows = 0
            for f in files:
                path = os.path.join(CHAIN_DIR, f)
                df = pd.read_parquet(path)
                total_rows += len(df)
                ts_col = "Timestamp" if "Timestamp" in df.columns else "timestamp"
                sym_col = "Symbol" if "Symbol" in df.columns else "symbol"
                strike_col = "Strike_Price" if "Strike_Price" in df.columns else "strike"
                timestamps = df[ts_col].nunique() if ts_col in df.columns else 1
                symbols = df[sym_col].nunique() if sym_col in df.columns else 1
                strikes = df[strike_col].nunique() if strike_col in df.columns else len(df)
                print(f"  {f}: {len(df)} rows, {timestamps} snapshots, {symbols} symbols, {strikes} strikes")
            print(f"Total: {len(files)} days, {total_rows} rows\n")

    if not os.path.isdir(DATA_DIR) and not os.path.isdir(CHAIN_DIR):
        print("No data collected yet")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Intraday OI + Option Chain Collector")
    parser.add_argument("--schedule", action="store_true", help="Every 15 min 9:20-15:29 + CAS at 15:42")
    parser.add_argument("--cas", action="store_true", help="Collect CAS closing prices now")
    parser.add_argument("--chain", action="store_true", help="Collect full option chain snapshot now")
    parser.add_argument("--options", action="store_true", help="Collect full option data snapshot now (alias to --chain)")
    parser.add_argument("--info", action="store_true", help="Show collected data summary")
    args = parser.parse_args()

    if args.info:
        show_info()
    elif args.cas:
        log.info("Collecting CAS closing prices...")
        cas_df = collect_cas_closing()
        if not cas_df.empty:
            save_cas_closing(cas_df)
            print(f"\nCAS closing prices for {len(cas_df)} symbols:")
            print(cas_df.to_string(index=False))
        else:
            print("No CAS data collected")
    elif args.chain or args.options:
        log.info("Collecting full options data snapshot...")
        chain_df = collect_chain_snapshot()
        if not chain_df.empty:
            save_chain_snapshot(chain_df)
            sym_col = "Symbol" if "Symbol" in chain_df.columns else ("symbol" if "symbol" in chain_df.columns else None)
            symbols = chain_df[sym_col].nunique() if sym_col else len(chain_df)
            print(f"\nCollected option data: {symbols} symbols, {len(chain_df)} contract rows")
            sample_cols = [c for c in [
                "Timestamp", "Symbol", "Expiry_Date", "Strike_Price", "Option_Type",
                "Open", "High", "Low", "Close", "Volume", "Open_Interest", "Bid_Price", "Ask_Price"
            ] if c in chain_df.columns]
            if sample_cols:
                print(chain_df[sample_cols].head(10).to_string(index=False))
        else:
            print("No chain data collected")
    elif args.schedule:
        run_schedule()
    else:
        log.info("Collecting single OI snapshot...")
        df = collect_snapshot()
        if not df.empty:
            save_snapshot(df)
            print(f"\nCollected {len(df)} symbols:")
            print(df[["symbol", "spot", "total_ce_oi", "total_pe_oi", "pcr"]].to_string(index=False))
        else:
            print("No data collected")
