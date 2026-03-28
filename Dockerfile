FROM freqtradeorg/freqtrade:stable
COPY freqtrade_strategy/config_btc_optimized.json /freqtrade/config.json
COPY freqtrade_strategy/pfaa_btc_strategy.py /freqtrade/user_data/strategies/pfaa_btc_strategy.py
RUN mkdir -p /freqtrade/user_data/data /freqtrade/user_data/logs
EXPOSE 8080
CMD ["webserver", "--config", "/freqtrade/config.json"]
