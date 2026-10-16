# NSE Options Data Collector

Automated data collection pipeline for NSE F&O — collects OI, full option chains (Greeks, IV, bid/ask), global cues, and EOD data for **37 symbols** (2 indices + 35 stocks). Saves to parquet files ready for ML/analysis.

Built for Upstox API. Uses the analytics token (valid 1 year, no daily refresh).
Instrument keys and lot sizes are resolved automatically from the API — just add a stock name and it works.

## What It Collects

| Collector | Schedule (IST) | Data |
|-----------|---------------|------|
| **Pre-market** | 8:45 AM, 10:00 AM | S&P 500, NASDAQ, Dow, US VIX, crude, gold, USDINR, DXY, Hang Seng, Nikkei |
| **OI Snapshot** | Every 15 min 9:20-15:29 (26/day) | OI summary, PCR, ATM bid/ask, max OI strikes, OI signals (long build/short cover) |
| **Option Chain** | Every 15 min 9:20-15:29 (26/day) | All strikes x CE/PE: OI, volume, LTP, bid, ask, IV, delta, theta, gamma, vega |
| **CAS Closing** | 15:42 | CAS-determined closing price + divergence from continuous close |
| **EOD** | 16:00 | 5-min candles (37 symbols), sector indices, FII/DII flows, VIX intraday, futures basis, market breadth |

### Symbols (37)

**Indices:** NIFTY, BANKNIFTY

**Stocks:** RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, BHARTIARTL, SBIN, ITC, LT, HINDUNILVR, KOTAKBANK, AXISBANK, MARUTI, SUNPHARMA, TITAN, BAJFINANCE, WIPRO, HCLTECH, ADANIENT, TATAMOTORS, TATASTEEL, POWERGRID, NTPC, ONGC, COALINDIA, JSWSTEEL, DRREDDY, BAJAJFINSV, ASIANPAINT, TECHM, INDUSINDBK, M&M, CIPLA, EICHERMOT, SBILIFE

## Quick Setup

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/nse-options-data-collector.git
cd nse-options-data-collector

# Install
pip install -r requirements.txt

# Configure — get token from https://account.upstox.com/developer/apps
cp .env.example .env
# Edit .env and paste your Upstox analytics token

# Test — collect a single snapshot
python examples/quick_start.py

# Run all collectors (full day)
python start_collectors.py
```

## Usage

### Automated daily collection
```bash
python start_collectors.py
```
Launches all 3 collectors in parallel. Runs from 8:45 AM to 4:15 PM IST. Press Ctrl+C to stop.

### Individual collectors
```bash
# OI + Chain (every 15 min)
python -m collectors.oi_collector --schedule

# Single snapshot
python -m collectors.oi_collector              # OI only
python -m collectors.oi_collector --chain      # Full chain only
python -m collectors.oi_collector --cas        # CAS closing only

# Pre-market global cues
python -m collectors.premarket_collector --schedule
python -m collectors.premarket_collector       # Single fetch

# EOD data
python -m collectors.eod_collector --schedule  # Wait for 16:00 then run
python -m collectors.eod_collector             # Run immediately
python -m collectors.eod_collector --candles   # 5-min candles only
python -m collectors.eod_collector --fii       # FII/DII only
python -m collectors.eod_collector --sectors   # Sector indices only
```

### Check collected data
```bash
python -m collectors.oi_collector --info
python -m collectors.eod_collector --info
python examples/explore_data.py
```

## Data Format

All data is saved as **parquet** files in `data/`:

```
data/
├── oi_snapshots/
│   ├── oi_2025-08-05.parquet        # 26 snapshots x 37 symbols/day
│   └── cas_2025-08-05.parquet       # CAS closing prices
├── option_chain/
│   └── chain_2025-08-05.parquet     # ~1400 strikes x 26 snapshots/day
├── global_cues/
│   └── global_2025-08-05.parquet    # Pre-market + Asian data
└── eod/
    ├── candles_5min/
    │   ├── NIFTY_2025-08-05.parquet
    │   └── RELIANCE_2025-08-05.parquet
    ├── sectors_2025-08-05.parquet
    ├── fii_dii_2025-08-05.parquet
    ├── futures_basis_2025-08-05.parquet
    └── breadth_2025-08-05.parquet
```

### OI Snapshot columns (26 per symbol per day)
`timestamp, symbol, expiry, spot, total_ce_oi, total_pe_oi, pcr, max_ce_oi, max_ce_oi_strike, max_pe_oi, max_pe_oi_strike, atm_strike, atm_ce_ltp, atm_ce_bid, atm_ce_ask, atm_pe_ltp, atm_pe_bid, atm_pe_ask, ce_oi_signal, pe_oi_signal, oi_change_pct, ce_oi_change_pct, pe_oi_change_pct, pcr_change`

### Option Chain / Options Data columns (normalized per contract row)
`Timestamp, Symbol, Open, High, Low, Close, Volume, Open_Interest, Expiry_Date, Strike_Price, Option_Type, Bid_Price, Ask_Price, Spot_Price, IV, Delta, Theta, Gamma, Vega`

Each option contract (Call / Put) is captured with full market data (OHLC, volume, open interest, quotes) and greeks. Saved to `data/option_chain/` as both Parquet and CSV files.

### Sample Data

Check `examples/sample_data/` for real CSV snapshots so you can see exactly what the collectors produce before running them:

| File | Description |
|------|-------------|
| `oi_snapshot_sample.csv` | 5-symbol OI snapshot (BANKNIFTY, RELIANCE, TCS, HDFCBANK, INFY) |
| `option_chain_sample.csv` | NIFTY ATM ±2 strikes with full Greeks (delta, theta, gamma, vega, IV) |
| `global_cues_sample.csv` | Pre-market (S&P, NASDAQ, crude, gold, USDINR) + Asian session (Hang Seng, Nikkei) |

## Adding Your Own Symbols

Just add the stock's NSE trading symbol to the `STOCKS` list in `config.py`:

```python
STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK",
    # ... existing stocks ...
    "BAJAJ-AUTO",   # <-- add your symbol here
    "TATAPOWER",
]
```

That's it. The collector automatically:
1. **Resolves instrument keys** via Upstox Symbol Search API (`/v2/instruments/search`) — no need to look up ISINs
2. **Fetches lot sizes** from the API (`/v2/option/contract`) — no hardcoded lot size tables
3. **Caches keys** to `data/oi_snapshots/_instrument_keys.json` so it only searches once per symbol

Also add the symbol to the `SYMBOLS` list in `collectors/eod_collector.py` if you want EOD candles for it.

## VPS Deployment (Oracle Cloud Free Tier)

Deploy to a free Oracle Cloud VM for automated daily collection without keeping your PC on.

### 1. Create VM
- Oracle Cloud Console → Compute → Instances → Create
- **Image:** Ubuntu 22.04
- **Shape:** VM.Standard.E2.1.Micro (free tier — 1 OCPU, 1GB RAM)
- **Boot volume:** 50GB (free tier, ~19 years of data)

### 2. Deploy
```bash
# From local PC — copy code to VPS
scp -i ~/.ssh/oracle_vps -r . ubuntu@YOUR_VPS_IP:~/nse-collector/

# SSH into VPS
ssh -i ~/.ssh/oracle_vps ubuntu@YOUR_VPS_IP

# Run setup
bash ~/nse-collector/deploy/setup_vps.sh

# Set token (NEVER copy your full .env)
echo "UPSTOX_ACCESS_TOKEN=your_token_here" > ~/nse-collector/.env

# Test
~/nse-collector/deploy/run_collectors.sh
```

### 3. Sync data to local PC
```bash
# Edit deploy/sync_data.sh — set your VPS_IP
bash deploy/sync_data.sh
```

Cron runs automatically: start at 8:15 AM, stop at 4:15 PM, weekdays only.

## Storage Estimate

| Data | Per Day | Per Month | Per Year |
|------|---------|-----------|----------|
| OI snapshots | ~250 KB | ~5.5 MB | ~65 MB |
| Option chain | ~9 MB | ~200 MB | ~2.4 GB |
| Global cues | ~5 KB | ~110 KB | ~1.3 MB |
| EOD data | ~500 KB | ~11 MB | ~130 MB |
| **Total** | **~10 MB** | **~220 MB** | **~2.6 GB** |

## API Notes

- Uses Upstox **analytics token** — valid for 1 year, no daily OAuth refresh
- Market data endpoints only — no order placement functions included
- Rate limiting handled automatically (429 backoff + retry)
- Network timeout retry with exponential backoff (up to 3 retries)
- NSE market hours: 9:15-15:30 IST. Pre-market 9:00-9:08 has limited data
- CAS auction: 15:30-15:40 IST. CAS closing price available after 15:40

## License

MIT
