#!/usr/bin/env bash
# Installs deps + the Kronos forecasting model. Skip the Kronos part to run with the EMA baseline.
set -e
pip install -r requirements.txt
mkdir -p vendor && [ -d vendor/Kronos ] || git clone --depth 1 https://github.com/shiyu-coder/Kronos vendor/Kronos
pip install -r vendor/Kronos/requirements.txt hf_xet  # hf_xet: Kronos weights are on Xet storage
