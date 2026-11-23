#!/bin/bash
aria2c --enable-rpc --rpc-listen-all=false --rpc-listen-port=6800 \
  --max-connection-per-server=16 --split=16 --min-split-size=10M \
  --seed-time=0 --daemon=true

python3 bot.py
