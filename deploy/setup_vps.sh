#!/bin/bash
# One-shot VPS setup script — run once after SSH into fresh Ubuntu VM
# Usage: bash setup_vps.sh

set -e

echo "=== Setting timezone to IST ==="
sudo timedatectl set-timezone Asia/Kolkata

echo "=== Installing Python 3.11 ==="
sudo apt update
sudo apt install -y python3.11 python3-pip python3.11-venv

echo "=== Creating project structure ==="
mkdir -p ~/nse-collector/data/oi_snapshots
mkdir -p ~/nse-collector/data/option_chain
mkdir -p ~/nse-collector/data/global_cues
mkdir -p ~/nse-collector/data/eod
mkdir -p ~/nse-collector/logs

echo "=== Creating virtual environment ==="
python3.11 -m venv ~/nse-collector/venv
source ~/nse-collector/venv/bin/activate

echo "=== Installing Python packages ==="
pip install --upgrade pip
pip install -r ~/nse-collector/requirements.txt

echo "=== Setting up cron jobs ==="
(crontab -l 2>/dev/null; cat <<'CRON'
# NSE Data Collectors — weekdays only
15 8 * * 1-5 ~/nse-collector/deploy/run_collectors.sh
15 16 * * 1-5 pkill -f start_collectors.py
0 0 * * 0 find ~/nse-collector/logs/ -name "*.log" -mtime +30 -delete
CRON
) | crontab -

echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Create .env:  echo 'UPSTOX_ACCESS_TOKEN=your_token' > ~/nse-collector/.env"
echo "  2. Test run:      ~/nse-collector/deploy/run_collectors.sh"
echo "  3. Check logs:    tail -f ~/nse-collector/logs/collector_\$(date +%Y-%m-%d).log"
