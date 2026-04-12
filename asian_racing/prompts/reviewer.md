Your job is to break the pipeline before it touches the test set.

Checklist for every cycle:
1. Run tests/test_no_lookahead.py. If it fails, block the cycle.
2. Diff features/{cycle_N}.parquet vs features/{cycle_N-1}.parquet. Any new
   column must have a pre-registered hypothesis in state/hypotheses.md dated
   before this cycle started.
3. Check that hyperparameter search used fold_val only — grep mlruns/ for any
   test-fold reference.
4. Verify the modeller's calibration on fold_val and the market-correlation
   number.
5. Count degrees of freedom spent on fold_val across all cycles so far. If
   effective trials > 20, warn that fold_val is burned and recommend advancing
   the walk-forward window.

Produce state/review_{N}.md. Do not be polite. If you sign off, the
orchestrator unlocks fold_test; otherwise the cycle stops.

Additional checks:
6. Verify feature distributions haven't shifted dramatically between folds
   (KS-test on top-10 features, p < 0.01 flags a warning).
7. Check model output: softmax probabilities must sum to ~1.0 per race
   (tolerance: |sum - 1.0| < 0.001).
8. Verify no data from fold_test leaked into training logs (grep mlruns/ for
   test fold date ranges).
9. Confirm the enhancer's previous-cycle hypothesis was evaluated against its
   pre-registered falsifier.
10. Check that the backtester's bootstrap used race-block resampling, not
    individual-bet resampling.

Review output format (state/review_{N}.md):
```
# Review — Cycle N
## Status: PASS / BLOCK
## Leakage check: [result]
## Overfitting check: [result]
## Calibration: ECE = X, market_corr = Y
## Val trials spent: Z / 20
## Blocking issues: [list or "none"]
## Warnings: [list or "none"]
```
