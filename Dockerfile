# PFAA FreqTrade — Production Dockerfile
FROM freqtradeorg/freqtrade:develop

# Copy strategy, config, and start script
COPY freqtrade_strategy/ /freqtrade/user_data/strategies/
COPY freqtrade_strategy/config_btc_optimized.json /freqtrade/config.json
COPY start.sh /freqtrade/start.sh

RUN mkdir -p /freqtrade/user_data/data /freqtrade/user_data/logs && \
    chmod +x /freqtrade/start.sh

EXPOSE 8080

# Smart start: trade mode if exchange loads, webserver fallback
ENTRYPOINT ["/bin/bash"]
CMD ["/freqtrade/start.sh"]
