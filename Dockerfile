# PFAA FreqTrade — Production Dockerfile
# Runs FreqTrade API server with v9 PFAABitcoinStrategy

FROM freqtradeorg/freqtrade:stable

# Copy strategy and config
COPY freqtrade_strategy/ /freqtrade/user_data/strategies/
COPY freqtrade_strategy/config_btc_optimized.json /freqtrade/config.json

# Create data directories
RUN mkdir -p /freqtrade/user_data/data /freqtrade/user_data/logs

# Render uses PORT env var (default 10000)
ENV PORT=8080
EXPOSE 8080

# Start in webserver mode — serves API + UI without needing exchange keys
# Switch to "trade" mode when you have Binance API keys configured
CMD ["webserver", \
     "--config", "/freqtrade/config.json", \
     "--strategy", "PFAABitcoinStrategy", \
     "--strategy-path", "/freqtrade/user_data/strategies"]
