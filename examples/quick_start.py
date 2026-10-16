"""
Quick Start — collect a single OI + chain snapshot and display results.

Usage:
    cd nse-options-data-collector
    python examples/quick_start.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from collectors.oi_collector import collect_snapshot, save_snapshot
from collectors.oi_collector import collect_chain_snapshot, save_chain_snapshot

print("=== Collecting OI Snapshot (37 symbols) ===\n")
oi_df = collect_snapshot()
if not oi_df.empty:
    save_snapshot(oi_df)
    print(f"\nCollected {len(oi_df)} symbols:")
    print(oi_df[["symbol", "spot", "total_ce_oi", "total_pe_oi", "pcr"]].to_string(index=False))
else:
    print("No OI data collected — check your UPSTOX_ACCESS_TOKEN")
    sys.exit(1)

print("\n=== Collecting Full Option Chain (all strikes) ===\n")
chain_df = collect_chain_snapshot()
if not chain_df.empty:
    save_chain_snapshot(chain_df)
    sym_col = "Symbol" if "Symbol" in chain_df.columns else "symbol"
    symbols = chain_df[sym_col].nunique()
    total_records = len(chain_df)
    print(f"\nCollected: {symbols} symbols, {total_records} option contract rows")
    print(f"\nSample (NIFTY near ATM contracts):")
    nifty = chain_df[chain_df[sym_col] == "NIFTY"]
    if not nifty.empty:
        strike_col = "Strike_Price" if "Strike_Price" in nifty.columns else "strike"
        spot_col = "Spot_Price" if "Spot_Price" in nifty.columns else ("spot" if "spot" in nifty.columns else None)
        spot = nifty[spot_col].iloc[0] if spot_col else 0
        if spot > 0:
            near_atm = nifty.iloc[(nifty[strike_col] - spot).abs().argsort()[:10]]
        else:
            near_atm = nifty.head(10)
        cols = [c for c in [
            "Timestamp", "Symbol", "Expiry_Date", "Strike_Price", "Option_Type",
            "Open", "High", "Low", "Close", "Volume", "Open_Interest", "Bid_Price", "Ask_Price"
        ] if c in near_atm.columns]
        if not cols:
            cols = list(near_atm.columns[:10])
        print(near_atm[cols].to_string(index=False))
    else:
        print(chain_df.head(10).to_string(index=False))
else:
    print("No chain data collected")

print("\n=== Data saved to data/ directory ===")
