# Model card: gozo_ferry, version 2

*Owner: Malcolm Debattista (ARI3217 practice project). Written for Session 6, Stage 15. Attached to the registered
version with `gozo-registry card 2 docs/model_card.md`.*

## Intended use

Gives, the day before, the probability that Gozo Channel ferry trips will be cancelled, from tomorrow's forecast
daily wind speed in knots. When the probability is 0.5 or more, the API returns a warning.

- **Who should rely on it:** planning and passenger-information staff, as an early signal to prepare (extra staff on
  the phones, a notice to travellers that sailings may be disrupted) and to watch the official updates more closely.
- **Who should not rely on it, and for what:**
  - the master of the ship, the operator or the port authority, deciding whether a ferry actually sails. That
    decision is made on the conditions at sea on the day, not on a forecast of the daily wind speed;
  - travellers deciding whether they can make an urgent trip (a hospital appointment, a flight from Malta).
    A "no warning" is not a promise that the ferry will sail;
  - anything about safety, refunds or compensation;
  - other routes or ports, or times of day: it predicts whole days, on this channel only.

## Model

Logistic regression on one feature, the wind speed converted from knots to km/h (factor 1.852, recorded as the run's
`knots_to_kmh` parameter). Trained with seed 42 by `gozo-train --train-start 2025-03-01`, code version 0.5.0,
commit `b95bd7a` (clean tree), MLflow run `7aafdaa5aefb47758a2800d5f591b14c`.

## Data

- **Training:** `data/gozo_ferry.csv`, the 250 days from 1 March to 5 November 2025, of which 7 had cancellations.
  The model is fitted on every day of the window. SHA-256 `ebd606dde638a982a5d3be651e8e2a38af81222217a229d4d558b02d8d0f74ba`.
- **Evaluation:** the frozen holdout `data/holdout.csv`, 56 days from 6 November to 31 December 2025, with 9
  cancelled days, never trained on. SHA-256 `fa8745708256b933415deaca764ce549328e69344b15280cccc7fa06dfc3d91d`.
- **One value per day:** the recorded daily wind speed and whether any trip was cancelled (0/1). Nothing about which
  trips, how many, or why.

## Metrics

On the frozen holdout, with a warning at probability 0.5 (about 28 knots for this version):

| Metric | Version 2 (champion) | Version 1 (challenger) |
|---|---|---|
| Recall (the gate metric, at least 0.75) | 0.889 (8 of 9 cancelled days warned) | 0.889 |
| Precision | 1.000 (no false warnings) | 0.889 (1 false warning) |
| Accuracy | 0.982 | 0.964 |
| ROC-AUC | 0.983 | 0.983 |

- **How sure:** with only 9 cancelled days in the holdout, the 95 % bootstrap interval for recall is 0.667 to 1.000
  for both versions. One more missed day would bring recall to 0.778, close to the gate.
- **Baseline:** always predicting "no cancellation" scores 0.839 accuracy and 0 recall.
- **Why version 2:** it passed the gate with the same recall as version 1 and gave one false warning fewer. That
  difference is a single day, well inside the interval, so the two versions are not clearly different.
- **Not registered:** a run trained only from 1 June 2025 (158 summer days, 2 cancelled) scored recall 0.556 and
  failed the gate. It is kept in MLflow as a tracked run.

## Limitations

What the model cannot know:

- **Sea state.** It sees wind only. Waves and swell left by a storm the day before, or arriving from a storm far
  away, can stop sailings on a day with moderate wind, and the model will not warn.
- **Wind direction.** A north-easterly and a south-westerly of the same speed get the same probability, although
  how exposed the channel and the harbours are depends on the direction.
- **Gusts and timing.** It uses one daily wind speed, so a short, strong gale in the morning looks the same as a
  steady breeze all day.
- **Forecast error.** It was trained on recorded wind but is used with tomorrow's forecast. If the forecast is
  wrong, the probability is wrong.
- **Other causes.** Technical faults, strikes, fog or port works also cancel trips. The model knows none of them.

Limits of the data:

- **Very few cancellations.** Version 2 learned from only 7 cancelled days, and its window leaves out the January
  and February storms. Version 1 learned from 23.
- **Wind range.** Version 2 saw winds up to 35.5 knots. Above that it extrapolates. Logistic regression keeps
  rising with the wind, so the warning stays on, but the exact probability is a guess.
- **One year.** Everything comes from 2025. A calm or stormy year, a new ship or new port rules would change the
  relationship.

## Monitoring

- The input-wind histogram on the Grafana dashboard (`docker compose --profile monitoring up -d`). A winter with
  more strong-wind days than 2025 is a reason to check the model again.
- The `predictions` table stores the registry version that made each prediction (`gozo_ferry/2`), so warnings can be
  matched to what actually happened once the day has passed, and recall and precision tracked per version.

## Rollback

- **To roll back:** `make champion V=1`. This moves the `champion` alias to version 1 and restarts the API, with no
  rebuild. The API is alive at once and ready once it has loaded the model from the registry.
- **Who may move the alias:** the model's owner. Record the reason in the project log.
- **Afterwards:** check that `/ready` and the newest rows of the `predictions` table both say `gozo_ferry/1`.
