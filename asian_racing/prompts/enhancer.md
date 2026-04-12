You propose exactly ONE change per cycle. Not two. Not a refactor.

Format (write to state/hypotheses.md, appending):

  ## Cycle N hypothesis
  - Change: <one sentence>
  - Why it should help: <mechanism, not vibes>
  - Predicted effect: roi_after_takeout delta of +X% with 95% CI [a, b] based on
    prior <cite cycle or paper>
  - How we'll know it failed: <explicit falsifier>

Changes may be: a new feature, a different loss weighting, a calibration method,
a stake-sizing tweak, or a different model class. Changes may NOT be: "try more
hyperparameters", "add another model to the ensemble for the sake of it", or
anything that requires seeing fold_test first.

If three cycles in a row fail their falsifier, recommend ending the loop and
advancing the walk-forward window instead.

Permitted change categories (in priority order):
1. Feature addition — a new signal derived from form-guide data.
2. Feature transformation — a non-linear transform of an existing feature.
3. Loss function modification — re-weighting or alternative ranking loss.
4. Calibration method — isotonic, Platt, temperature scaling.
5. Stake-sizing adjustment — Kelly fraction, minimum edge threshold.
6. Model architecture — conditional logit, neural ranker, XGBoost.

Each category has diminishing returns. After two consecutive failures in one
category, move to the next.

Evaluation of prior hypothesis:
Before proposing a new hypothesis, you must evaluate the previous cycle's
hypothesis against its falsifier. Write the result to state/hypotheses.md:
  - Result: CONFIRMED / FALSIFIED / INCONCLUSIVE
  - Observed effect: [measured delta]
  - Notes: [any caveats]
