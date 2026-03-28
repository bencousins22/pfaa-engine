# PFAA FreqTrade — Production Dockerfile for Railway
# Runs FreqTrade with the v9 optimized PFAABitcoinStrategy

FROM freqtradeorg/freqtrade:stable

# Copy strategy and config
COPY freqtrade_strategy/ /freqtrade/user_data/strategies/
COPY freqtrade_strategy/config_btc_optimized.json /freqtrade/config.json

# Create data directories
RUN mkdir -p /freqtrade/user_data/data /freqtrade/user_data/logs

# Expose API port for FreqUI
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
    CMD curl -f http://localhost:8080/api/v1/ping || exit 1

# Run FreqTrade in trade mode
CMD ["trade", \
     "--config", "/freqtrade/config.json", \
     "--strategy", "PFAABitcoinStrategy", \
     "--strategy-path", "/freqtrade/user_data/strategies"]
