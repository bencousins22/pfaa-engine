# Asian Racing Prediction — Claude Opus 4.6 Agent Team

Specialised agent team that predicts Asian thoroughbred races (HKJC, JRA) from
pre-race form guides, backtests with strict walk-forward validation, and runs a
self-improvement loop that cannot see the held-out future.

## Architecture

```
asian_racing/
├── prompts/              # 7 agent system prompts
│   ├── orchestrator.md   # Coordinates team, manages cycle state
│   ├── data_steward.md   # Data acquisition + temporal integrity
│   ├── feature_engineer.md # Leak-free feature construction
│   ├── modeller.md       # LightGBM ranking (win-log-loss)
│   ├── backtester.md     # Walk-forward + Kelly staking
│   ├── reviewer.md       # Adversarial audit (leakage, overfitting)
│   ├── enhancer.md       # Pre-registered single-change proposals
│   └── cycle_kickoff.md  # User turn template
├── src/                  # Python implementation
│   ├── features.py       # Feature engineering (12 baseline features)
│   ├── modeller.py       # LightGBM ranker + conditional logit baseline
│   ├── backtester.py     # Walk-forward backtest + bootstrap CI
│   ├── reviewer.py       # Adversarial review checklist
│   ├── data_steward.py   # Data loading + validation
│   ├── orchestrator.py   # End-to-end cycle runner
│   └── api_runner.py     # Claude API dispatch for agent team
├── schema/               # SQL schema (races, runners)
├── tests/                # Leak detection + unit tests
├── features/             # Feature parquets per fold
├── models/               # Saved LightGBM models per cycle
├── reports/              # Backtest reports per cycle
└── state/                # Hypothesis tree, manifests, reviews
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run a cycle with local data
python -m asian_racing.src.orchestrator \
  --races data/races.parquet \
  --runners data/runners.parquet \
  --train-end "2023-07-01" \
  --val-end "2024-01-01"

# Run via Claude API (requires ANTHROPIC_API_KEY)
python -m asian_racing.src.api_runner --cycle 1

# Dry run (no API key needed)
python -m asian_racing.src.api_runner --cycle 1 --dry-run

# Run tests
pytest tests/ -v
```

## Agent Team

| Agent | Role | Effort | Model |
|-------|------|--------|-------|
| orchestrator | Plans, dispatches, synthesises | high | Opus 4.6 |
| data-steward | Data acquisition, temporal integrity | low | Haiku 4.5 |
| feature-engineer | Leak-free features from form guide | adaptive | Opus 4.6 |
| modeller | Ranking model (softmax, win-log-loss) | adaptive | Opus 4.6 |
| backtester | Walk-forward + Kelly + bootstrap ROI | adaptive | Opus 4.6 |
| reviewer | Adversarial audit (non-optional) | high | Opus 4.6 |
| enhancer | Single pre-registered change per cycle | high | Opus 4.6 |

## Anti-P-Hacking Guards

1. **One change per cycle, pre-registered** — enhancer writes its prediction
   before seeing results.
2. **Validation-trial budget** — reviewer counts trials on fold_val; at 20,
   it's declared burned.
3. **Block-bootstrap ROI floor** — 5th percentile of race-block bootstrap must
   be >= 0% to claim edge.

## Success Bar

5th-percentile bootstrap ROI after takeout >= 0% on two consecutive walk-forward
windows. Anything stronger deserves extraordinary scrutiny.
