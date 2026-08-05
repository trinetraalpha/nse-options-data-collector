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
    symbols = chain_df["symbol"].nunique()
    strikes = len(chain_df)
    print(f"\nCollected: {symbols} symbols, {strikes} strike rows")
    print(f"\nSample (NIFTY ATM +/- 2 strikes):")
    nifty = chain_df[chain_df["symbol"] == "NIFTY"]
    if not nifty.empty:
        spot = nifty["spot"].iloc[0]
        near_atm = nifty.iloc[(nifty["strike"] - spot).abs().argsort()[:5]]
        print(near_atm[["strike", "ce_ltp", "ce_iv", "ce_delta", "ce_oi",
                         "pe_ltp", "pe_iv", "pe_delta", "pe_oi"]].to_string(index=False))
else:
    print("No chain data collected")

print("\n=== Data saved to data/ directory ===")
