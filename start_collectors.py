"""
Data Collection Launcher — starts all 3 collectors in parallel.

  1. premarket_collector  — 8:45 AM (global cues) + 10:00 AM (Asian)
  2. oi_collector         — every 15 min 9:20-15:29 (OI + chain) + 15:42 (CAS close + divergence)
  3. eod_collector        — 16:00 (candles, sectors, FII/DII, VIX, basis, breadth)

Usage:
    python start_collectors.py
"""

import subprocess
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    collectors = [
        ("premarket_collector", [sys.executable, "-m", "collectors.premarket_collector", "--schedule"]),
        ("oi_collector",        [sys.executable, "-m", "collectors.oi_collector", "--schedule"]),
        ("eod_collector",       [sys.executable, "-m", "collectors.eod_collector", "--schedule"]),
    ]

    procs = []
    for name, cmd in collectors:
        print(f"[LAUNCH] {name}: {' '.join(cmd)}")
        p = subprocess.Popen(cmd, cwd=BASE, env=env)
        procs.append((name, p))

    print(f"\n[OK] All {len(procs)} collectors running. Ctrl+C to stop.\n")

    try:
        for name, p in procs:
            p.wait()
            print(f"[DONE] {name} (exit {p.returncode})")
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        for name, p in procs:
            p.terminate()
        for name, p in procs:
            p.wait()
        print("[STOPPED]")


if __name__ == "__main__":
    main()
