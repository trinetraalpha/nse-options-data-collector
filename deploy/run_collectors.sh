#!/bin/bash
# Wrapper for cron — activates venv and runs collectors with logging
source ~/nse-collector/venv/bin/activate
cd ~/nse-collector
python start_collectors.py >> ~/nse-collector/logs/collector_$(date +%Y-%m-%d).log 2>&1
