You train a ranking model that predicts P(win) for each runner, softmaxed across
the runners in a single race. Loss = -log(p_winner) (Koker's win-log-loss).

Default model: gradient-boosted ranker (LightGBM with objective=lambdarank,
group=field_size_per_race). Keep a linear baseline (conditional logit) for
sanity comparison.

Rules:
- Train on fold_train only. Hyperparameter search uses fold_val only. Never
  touch fold_test.
- Log every run to mlruns/ with feature hash, data hash, seed.
- Output models/{cycle_N}.lgb and a calibration curve on fold_val. If ECE on
  fold_val > 0.05, stop and request recalibration before backtest.
- Report top-3 feature importances and the correlation between your p_win and
  the market's implied probability. If correlation > 0.97 you have no edge;
  say so.

Model training protocol:
1. Load features/{fold_train}.parquet and features/{fold_val}.parquet.
2. Construct LightGBM Dataset with group parameter = field sizes per race.
3. Train with early stopping on fold_val (patience=50 rounds).
4. Compute softmax probabilities per race on fold_val.
5. Compute calibration: ECE (10-bin), reliability diagram, Brier score.
6. Compute market correlation: Pearson(p_model, 1/SP_decimal) per race.
7. Log all metrics to mlruns/cycle_{N}/metrics.json.
8. Save model to models/cycle_{N}.lgb.

Hyperparameter search space (Optuna, 50 trials max on fold_val):
- learning_rate: [0.01, 0.3]
- num_leaves: [15, 127]
- min_data_in_leaf: [5, 50]
- feature_fraction: [0.5, 1.0]
- bagging_fraction: [0.5, 1.0]
- lambda_l1: [0, 5]
- lambda_l2: [0, 5]
