#!/bin/bash
# Sync collected data from VPS to local PC
# Usage: bash deploy/sync_data.sh
#
# Edit VPS_IP and KEY before first use

VPS_IP="REPLACE_WITH_YOUR_VPS_IP"
KEY="~/.ssh/oracle_vps"
LOCAL_DATA="./data/"

if [ "$VPS_IP" = "REPLACE_WITH_YOUR_VPS_IP" ]; then
    echo "ERROR: Edit this script and set VPS_IP first"
    exit 1
fi

echo "Syncing data from $VPS_IP..."
rsync -avz -e "ssh -i $KEY" ubuntu@$VPS_IP:~/nse-collector/data/ $LOCAL_DATA

echo ""
echo "=== Synced files ==="
for dir in oi_snapshots option_chain global_cues eod; do
    count=$(ls ${LOCAL_DATA}${dir}/ 2>/dev/null | wc -l)
    echo "  $dir: $count files"
done
