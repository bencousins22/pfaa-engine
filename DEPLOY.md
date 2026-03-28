# PFAA FreqTrade — Deployment Guide

## Quick Start (Docker Compose — Local)

```bash
# 1. Copy env template and fill in your Binance API keys
cp .env.example .env
# Edit .env with your BINANCE_API_KEY and BINANCE_API_SECRET

# 2. Start FreqTrade + FreqUI
docker-compose up -d

# 3. Access
# FreqTrade API: http://localhost:8080
# FreqUI:        http://localhost:8081
# Login:         pfaa / pfaa2026
```

## Railway Deployment

### Option A: Single Service (FreqTrade Backend)

1. Connect repo to Railway: `https://railway.app/new`
2. Select `bencousins22/pfaa-engine`
3. Railway auto-detects `Dockerfile` and `railway.toml`
4. Add environment variables:
   - `BINANCE_API_KEY` — your Binance API key
   - `BINANCE_API_SECRET` — your Binance secret
   - `FREQTRADE_API_USER` — API username (default: pfaa)
   - `FREQTRADE_API_PASS` — API password (change this!)
   - `FREQTRADE_JWT_SECRET` — random secret for JWT tokens
5. Deploy — Railway builds and runs the FreqTrade bot
6. Note the Railway URL (e.g., `https://pfaa-freqtrade-xxx.up.railway.app`)

### Option B: Full Stack (FreqTrade + FreqUI)

1. In Railway, create a new project
2. Add first service: **FreqTrade Backend**
   - Source: this repo
   - Dockerfile: `Dockerfile`
   - Add env vars (see above)
   - Expose port 8080
3. Add second service: **FreqUI Frontend**
   - Source: this repo
   - Dockerfile: `Dockerfile.frequi`
   - No env vars needed
   - Expose port 80
4. In FreqUI, set the backend URL to the FreqTrade service's Railway URL

### Option C: Docker Compose on Railway

Railway supports docker-compose directly:
1. Connect repo
2. Railway detects `docker-compose.yml`
3. Both services deploy automatically
4. Add env vars to the FreqTrade service

## Configuration

### Strategy: PFAABitcoinStrategy (v9)
- **Return**: +135.8% on 15-month backtest
- **Win Rate**: 57.4%
- **Max Drawdown**: 25.4%
- **Config**: `freqtrade_strategy/config_btc_optimized.json`

### Important Settings

| Setting | Value | Notes |
|---------|-------|-------|
| `dry_run` | `true` | **Change to `false` for live trading** |
| `dry_run_wallet` | `10000` | Paper trading balance |
| `max_open_trades` | `1` | Single BTC position only |
| `stake_amount` | `0.95` | 95% of balance per trade |
| `exchange.name` | `binance` | Change for other exchanges |
| `api_server.enabled` | `true` | Required for FreqUI |
| `api_server.username` | `pfaa` | Change in production |
| `api_server.password` | `pfaa2026` | **CHANGE IN PRODUCTION** |

### Going Live

1. Set `dry_run: false` in config
2. Use real Binance API keys with trading permissions
3. Start with small amounts ($100-$500)
4. Monitor via FreqUI for at least 1 week before scaling
5. Set up Telegram alerts for trade notifications

### Monitoring

```bash
# Check bot status
docker-compose logs -f freqtrade

# FreqTrade CLI inside container
docker-compose exec freqtrade freqtrade show-trades --config /freqtrade/config.json

# Download fresh data
docker-compose exec freqtrade freqtrade download-data \
  --config /freqtrade/config.json \
  --timeframes 5m 1h \
  --timerange 20250101-20260401

# Run hyperopt (inside container)
docker-compose exec freqtrade freqtrade hyperopt \
  --config /freqtrade/config.json \
  --strategy PFAABitcoinStrategy \
  --strategy-path /freqtrade/user_data/strategies \
  --hyperopt-loss CalmarHyperOptLoss \
  --epochs 1000 \
  --spaces buy sell stoploss roi
```

## Architecture

```
┌──────────────────┐     ┌──────────────────┐
│   FreqUI (Nginx) │────►│ FreqTrade (API)  │
│   Port 8081/80   │     │   Port 8080      │
│   Web Dashboard  │     │   Trading Bot    │
└──────────────────┘     └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │  Binance API      │
                         │  BTC/USDT Spot    │
                         └──────────────────┘
```
