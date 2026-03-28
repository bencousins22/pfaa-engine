#!/bin/bash
set -e
echo "PFAA FreqTrade pfaa-crypto-team starting..."
echo "Attempting trade mode..."

# Try trade mode first — if exchange loads, great
timeout 120 freqtrade trade \
  --config /freqtrade/config.json \
  --strategy PFAABitcoinStrategy \
  --strategy-path /freqtrade/user_data/strategies &
PID=$!

# Wait for it to either stabilize or crash
sleep 30

if kill -0 $PID 2>/dev/null; then
    echo "Trade mode running (PID $PID)"
    wait $PID
else
    echo "Trade mode failed — falling back to webserver mode"
    exec freqtrade webserver --config /freqtrade/config.json
fi
