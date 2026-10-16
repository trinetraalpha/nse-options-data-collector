"""
Explore collected data — read parquet files and analyze.

Usage:
    cd nse-options-data-collector
    python examples/explore_data.py
"""

import os
import sys
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def show_oi():
    oi_dir = os.path.join(DATA_DIR, "oi_snapshots")
    if not os.path.isdir(oi_dir):
        print("No OI data yet. Run: python examples/quick_start.py")
        return

    files = sorted(f for f in os.listdir(oi_dir) if f.startswith("oi_") and f.endswith(".parquet"))
    print(f"=== OI Snapshots ({len(files)} days) ===")
    for f in files:
        df = pd.read_parquet(os.path.join(oi_dir, f))
        ts = df["timestamp"].nunique()
        syms = df["symbol"].nunique()
        print(f"  {f}: {ts} snapshots, {syms} symbols, {len(df)} rows")

    if files:
        latest = pd.read_parquet(os.path.join(oi_dir, files[-1]))
        last_ts = latest["timestamp"].max()
        snap = latest[latest["timestamp"] == last_ts]
        print(f"\nLatest snapshot ({last_ts[:19]}):")
        print(snap[["symbol", "spot", "pcr", "ce_oi_signal", "pe_oi_signal",
                     "oi_change_pct"]].to_string(index=False))


def show_chain():
    chain_dir = os.path.join(DATA_DIR, "option_chain")
    if not os.path.isdir(chain_dir):
        return

    files = sorted(f for f in os.listdir(chain_dir) if f.startswith("chain_") and f.endswith(".parquet"))
    print(f"\n=== Option Chain / Options Data ({len(files)} days) ===")
    for f in files:
        df = pd.read_parquet(os.path.join(chain_dir, f))
        ts_col = "Timestamp" if "Timestamp" in df.columns else "timestamp"
        sym_col = "Symbol" if "Symbol" in df.columns else "symbol"
        ts = df[ts_col].nunique() if ts_col in df.columns else 1
        syms = df[sym_col].nunique() if sym_col in df.columns else 1
        print(f"  {f}: {ts} snapshots, {syms} symbols, {len(df)} rows")

    if files:
        latest = pd.read_parquet(os.path.join(chain_dir, files[-1]))
        ts_col = "Timestamp" if "Timestamp" in latest.columns else "timestamp"
        sym_col = "Symbol" if "Symbol" in latest.columns else "symbol"
        last_ts = latest[ts_col].max() if ts_col in latest.columns else None
        subset = latest[latest[ts_col] == last_ts] if last_ts is not None else latest.copy()
        nifty = subset[subset[sym_col] == "NIFTY"] if sym_col in subset else subset
        if not nifty.empty:
            strike_col = "Strike_Price" if "Strike_Price" in nifty.columns else "strike"
            spot_col = "Spot_Price" if "Spot_Price" in nifty.columns else ("spot" if "spot" in nifty.columns else None)
            spot = nifty[spot_col].iloc[0] if spot_col else 0
            print(f"\nNIFTY Options Data Snapshot (spot={spot}):")
            if strike_col in nifty.columns and spot > 0:
                near = nifty.iloc[(nifty[strike_col] - spot).abs().argsort()[:10]]
            else:
                near = nifty.head(10)
            cols = [c for c in [
                "Timestamp", "Symbol", "Expiry_Date", "Strike_Price", "Option_Type",
                "Open", "High", "Low", "Close", "Volume", "Open_Interest", "Bid_Price", "Ask_Price"
            ] if c in near.columns]
            if not cols:
                cols = list(near.columns[:10])
            print(near[cols].to_string(index=False))

        crude = subset[subset[sym_col] == "CRUDEOIL"] if sym_col in subset else None
        if crude is not None and not crude.empty:
            spot_col = "Spot_Price" if "Spot_Price" in crude.columns else ("spot" if "spot" in crude.columns else None)
            spot = crude[spot_col].iloc[0] if spot_col else 0
            print(f"\nCRUDEOIL MCX Options Data (step=500, spot={spot}):")
            cols = [c for c in [
                "Timestamp", "Symbol", "Expiry_Date", "Strike_Price", "Option_Type",
                "Open", "High", "Low", "Close", "Volume", "Open_Interest", "Bid_Price", "Ask_Price"
            ] if c in crude.columns]
            print(crude[cols].head(10).to_string(index=False))


def show_global():
    global_dir = os.path.join(DATA_DIR, "global_cues")
    if not os.path.isdir(global_dir):
        return

    files = sorted(f for f in os.listdir(global_dir) if f.endswith(".parquet"))
    print(f"\n=== Global Cues ({len(files)} days) ===")
    if files:
        latest = pd.read_parquet(os.path.join(global_dir, files[-1]))
        for _, row in latest.iterrows():
            session = row.get("session", "?")
            cols = [c for c in row.index if c.endswith("_chg_pct")]
            changes = {c.replace("_chg_pct", ""): f"{row[c]:+.2f}%" for c in cols if row[c] != 0}
            print(f"  {session}: {changes}")


if __name__ == "__main__":
    show_oi()
    show_chain()
    show_global()
