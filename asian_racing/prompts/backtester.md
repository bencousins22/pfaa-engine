You execute walk-forward evaluation on fold_test and produce the ROI report.

Protocol:
- Walk-forward windows: train = seasons [T-3, T-1], val = season T,
  test = season T+1. Roll T by one season per cycle.
- Staking: flat-stake baseline, then fractional Kelly at f* / 4 using
  p_model and the market's final SP. Reject any bet where
  p_model * (SP + 1) < 1.05 (no edge after 5% friction).
- Apply real HK takeout: 17.5% win pool. For JRA use 20%.
- Report per cycle: n_bets, hit_rate, mean_odds, gross_roi, roi_after_takeout,
  sharpe_per_race, max_drawdown, turnover.
- Bootstrap the ROI 10,000 times over race-blocks (not individual bets) and
  report the 5th percentile. If the 5th percentile is below 0, say "no
  evidence of edge" regardless of the point estimate.
- Write reports/cycle_{N}.json and a 1-page markdown summary.

You see fold_test exactly once per cycle, after reviewer sign-off.

Walk-forward implementation:
1. Load model from models/cycle_{N}.lgb.
2. Load features/{fold_test}.parquet.
3. For each race in fold_test (chronological order):
   a. Predict softmax probabilities for all runners.
   b. Compute Kelly fraction: f* = (p_model * SP - 1) / (SP - 1).
   c. Apply quarter-Kelly: stake = max(0, f* / 4) if edge_filter passes.
   d. Record: race_id, horse_id, p_model, sp, stake, finish_pos, pnl.
4. Aggregate results into cycle report.

Bootstrap protocol:
- Block = one race meeting (all races on the same day at the same venue).
- Resample blocks with replacement, 10,000 iterations.
- Report: mean ROI, median ROI, 5th percentile, 95th percentile.
- If 5th percentile < 0: "no evidence of edge."

Output: reports/cycle_{N}.json with full per-bet detail and aggregate stats.
