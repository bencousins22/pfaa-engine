# PFAA FreqTrade — Production Dockerfile (Hyperliquid)
FROM freqtradeorg/freqtrade:develop

# Copy strategy and config
COPY freqtrade_strategy/ /freqtrade/user_data/strategies/
COPY freqtrade_strategy/config_btc_optimized.json /freqtrade/config.json

# Create data directories
RUN mkdir -p /freqtrade/user_data/data /freqtrade/user_data/logs

EXPOSE 8080

# Start FreqTrade in dry-run trade mode on Hyperliquid
CMD ["trade", \
     "--config", "/freqtrade/config.json", \
     "--strategy", "PFAABitcoinStrategy", \
     "--strategy-path", "/freqtrade/user_data/strategies"]
