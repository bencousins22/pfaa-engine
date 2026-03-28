# PFAA FreqTrade — Production Dockerfile
FROM freqtradeorg/freqtrade:stable

# Copy strategy and config
COPY freqtrade_strategy/ /freqtrade/user_data/strategies/
COPY freqtrade_strategy/config_btc_optimized.json /freqtrade/config.json

# Create data directories
RUN mkdir -p /freqtrade/user_data/data /freqtrade/user_data/logs

EXPOSE 8080

# Use a startup script that handles missing exchange keys gracefully
RUN printf '#!/bin/bash\nset -e\necho "PFAA FreqTrade v9 starting..."\nif [ -n "$BINANCE_API_KEY" ] && [ "$BINANCE_API_KEY" != "" ]; then\n  echo "Binance API key found — starting in TRADE mode"\n  exec freqtrade trade --config /freqtrade/config.json --strategy PFAABitcoinStrategy --strategy-path /freqtrade/user_data/strategies\nelse\n  echo "No Binance API key — starting in WEBSERVER mode (API only)"\n  exec freqtrade webserver --config /freqtrade/config.json\nfi\n' > /freqtrade/start.sh && chmod +x /freqtrade/start.sh

CMD ["/freqtrade/start.sh"]
