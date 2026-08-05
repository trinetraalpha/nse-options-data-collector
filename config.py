"""
Configuration — symbols, paths, lot sizes.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
LOG_DIR  = ROOT_DIR / "logs"

LOT_SIZES = {
    "NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 65,
    "RELIANCE": 250, "TCS": 175, "HDFCBANK": 550, "INFY": 300,
    "ICICIBANK": 700, "BHARTIARTL": 475, "SBIN": 750, "ITC": 1600,
    "LT": 150, "HINDUNILVR": 300, "KOTAKBANK": 400, "AXISBANK": 625,
    "MARUTI": 100, "SUNPHARMA": 350, "TITAN": 375, "BAJFINANCE": 125,
    "WIPRO": 1500, "HCLTECH": 350, "ADANIENT": 250, "TATAMOTORS": 1400,
    "TATASTEEL": 5500, "POWERGRID": 2700, "NTPC": 2250, "ONGC": 3250,
    "COALINDIA": 1700, "JSWSTEEL": 900, "DRREDDY": 125, "BAJAJFINSV": 500,
    "ASIANPAINT": 300, "TECHM": 600, "INDUSINDBK": 700, "M&M": 350,
    "CIPLA": 650, "EICHERMOT": 150, "SBILIFE": 750,
}

STRIKE_STEP = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50}

INDICES = ["NIFTY", "BANKNIFTY"]
STOCKS = [s for s in LOT_SIZES if s not in INDICES and s != "FINNIFTY"]
ALL_SYMBOLS = INDICES + STOCKS

INSTRUMENT_KEYS = {
    "NIFTY":     "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY":  "NSE_INDEX|Nifty Fin Service",
    "VIX":       "NSE_INDEX|India VIX",
}


def load_env(path: Path = None) -> int:
    """Load .env file into os.environ. Returns count of vars loaded."""
    env_path = path or (ROOT_DIR / ".env")
    if not env_path.is_file():
        return 0

    loaded = 0
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
                loaded += 1
    return loaded
