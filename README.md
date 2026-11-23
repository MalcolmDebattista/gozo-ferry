# Gozo Channel ferry model

Predicts the probability that Gozo Channel ferry trips are cancelled tomorrow,
from the forecast daily wind speed. The data records wind in knots; the model is
trained on km/h, using the conversion in `gozo_ferry.features.knots_to_kmh`.

## Requirements

Python 3.12 with the venv module. On Ubuntu:

```bash
sudo apt install python3 python3-venv
```

## Install

Run these from this folder, the one with pyproject.toml:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m pip install -e ".[dev]"
cp env.example .env
```

## Test

```bash
pytest
```

## Train

```bash
gozo-train
```

The model is saved to models/model.joblib. Shared settings (data path, seed,
warning threshold) are in config/config.yaml; settings for your
machine go in .env.

## Run the API

Train first, then:

```bash
uvicorn gozo_ferry.api:app --port 8888
```

Endpoints:

- `GET /health` returns `{"status": "ok"}`.
- `POST /predict` takes tomorrow's forecast wind speed **in knots** and returns
  the probability of cancellations and whether a warning should be issued
  (probability at or above `warning_threshold` in config/config.yaml).

```bash
curl -X POST localhost:8888/predict -H "Content-Type: application/json" -d '{"wind": 30}'
# {"wind":30.0,"probability_cancelled":0.73,"warning":true}
# (0.726 before Stage 12; the model now trains on the 309 days before the holdout)
```

The API converts knots to km/h with the same function used in training, so a
request gives the same probability as the training code (no training-serving skew).

## Run in Docker

```bash
docker build -t gozo-ferry:0.1 .
docker run -d --name gozo-api -p 8888:8888 gozo-ferry:0.1
curl localhost:8888/health
curl -X POST localhost:8888/predict -H "Content-Type: application/json" -d '{"wind": 30}'
time docker stop gozo-api     # should take well under a second
docker rm gozo-api
```

The image trains the model during the build, so it contains its own copy of the
model and of config.yaml. After changing either, rebuild the image; restarting the
container is not enough.

## Store predictions (Stage 10)

`compose.yaml` runs the API (`gozo-ferry:0.2`) next to a Postgres database. Every
prediction is saved to the `predictions` table (see db/init.sql) with the time, the
wind speed **in knots as received**, the probability, whether a warning was issued,
and the model version. Set `DB_PASSWORD` in `.env` first (see env.example).

```bash
docker compose up -d --build
curl -X POST localhost:8888/predict -H "Content-Type: application/json" -d '{"wind": 12}'
curl -X POST localhost:8888/predict -H "Content-Type: application/json" -d '{"wind": 30}'
docker compose exec db psql -U gozo -d gozo -c "SELECT * FROM predictions;"
docker compose down          # add -v to also delete the stored predictions
```

## Monitoring (Stage 11)

The API exposes Prometheus metrics at `GET /metrics`, with the same names as the
shop model so the provided Grafana dashboard works unchanged:

- `predictions_total`: number of predictions served
- `prediction_latency_seconds`: time to answer a prediction request
- `prediction_input`: forecast wind speed **in knots, as received**
  (buckets 5, 10, 15, 20, 25, 30, 35, 40, 50, 60)

The `monitoring/` folder is copied unchanged from the shop project and included
from compose.yaml. Stop the shop services first (`docker compose down` in the shop
folder) so ports 8888, 9090 and 3000 are free.

```bash
docker compose up -d --build          # api (gozo-ferry:0.3), db, prometheus, grafana
python3 monitoring/traffic.py --field wind --mean 12 --sd 5 --duration 300   # ordinary days
python3 monitoring/traffic.py --field wind --mean 22 --sd 6 --duration 300   # stormy winter
```

Open Grafana at http://localhost:3000. During the stormy run, the average input
value jumps from about 12 to about 22 knots, while request rate and latency stay
the same: input drift does not show up in the service metrics.


## The pipeline (Stage 12)

One command runs every check, in order, and stops at the first failure:

```bash
make ci        # = make lint test validate gate build
```

| Target | What it does | Fails when |
|---|---|---|
| `make install` | Installs the pinned requirements and the package with its dev tools | pip fails |
| `make lint` | `ruff` checks the code (rule set pinned in pyproject.toml) | A rule is broken |
| `make test` | `pytest`: unit tests, API tests, range tests and tests of the checks themselves (19) | Any test fails |
| `make validate` | `gozo-validate`: both data files against a pandera schema, then the split | A date, wind or label is invalid, a day repeats, or the holdout overlaps the training data |
| `make gate` | `gozo-gate`: trains on the days before the holdout and scores the frozen holdout | Exit 1: below the threshold; 2: holdout changed; 3: file missing |
| `make build` | Builds `gozo-ferry:<version>` and `gozo-ferry:<version>-<commit>` | The image does not build |
| `make publish` | Pushes both tags (used by CI on main only) | The push is refused |
| `make up` | Starts the services with the version from pyproject.toml | compose fails |
| `make version` | Prints the version (one place: pyproject.toml) | |

`make gate GATE_SPLIT=random` scores a random 20 % of the training window instead, for comparison.

### Data and the frozen holdout

`data/gozo_ferry.csv` holds the 309 days from 1 January to 5 November 2025. `data/holdout.csv` holds the last
eight weeks (56 days from 6 November 2025). It was cut once and is never edited or trained on, and its SHA-256 is
in `config/config.yaml`. `.gitattributes` stops git changing its line endings. Wind is in **knots** in the files,
the schema and the range test; the model still receives km/h through `knots_to_kmh`.

### The quality gate

**Metric: recall on cancelled days, threshold 0.75.** Crossings are cancelled on about one day in ten (16 % of the
holdout), so a model that never warns is already 84 % accurate, and accuracy would hide the error that matters
most: a cancellation with no warning leaves passengers and freight stranded at Ċirkewwa or Mġarr. Recall asks how
many cancelled days got a warning. 0.75 means at least three in four, and `gozo-gate` still prints precision so a
model that simply warns every day is visible.

Result on the frozen holdout: recall **0.889** (8 of 9 cancelled days warned; 95 % interval 0.667 to 1.000),
precision 0.889, accuracy 0.964 against a 0.839 do-nothing baseline: **GATE PASS**. The interval is wide because
the holdout has only 9 cancelled days, so one more missed day moves recall by 11 points.

## Continuous integration (Stage 13)

`.github/workflows/ci.yml` runs on every push and pull request. GitHub starts a fresh Ubuntu machine, installs
Python 3.12 and the project, copies `env.example` to `.env` (placeholders only), and runs the same `make ci`.
A pull request with a bad row goes red at `validate`.

On a push to `main`, and only if every check passed, the workflow logs in to GitHub's registry with the run's own
temporary token and publishes the image it just built and checked:
`ghcr.io/<your-github-name>/gozo-ferry:0.4.0` and `ghcr.io/<your-github-name>/gozo-ferry:0.4.0-<commit>`.

**To release a new version**, change `version` in `pyproject.toml` and push to `main`. The image tag and
`MODEL_VERSION` follow automatically.

To block merges on a red check, add a branch rule for `main` that requires the `ci` check (Settings > Branches).

## Track and register runs (Stage 14)

An MLflow tracking server and model registry runs as the `mlflow` service, on port 5000. It keeps its records in
a second Postgres database, `mlflow`, and the model files in the `mlflow-artifacts` volume. Prometheus and Grafana
now start only when asked (`docker compose --profile monitoring up -d`), to leave memory for MLflow.

```bash
docker compose up -d db mlflow
docker compose exec db createdb -U gozo mlflow   # only if the db volume existed before Stage 14
make register                                   # train, track the run, register it if it passed the gate
make register TRAIN_START=2025-03-01            # another training window ('none' = every day)
gozo-registry show                              # versions, their holdout scores, and aliases
gozo-registry alias champion 2
```

Every `gozo-train` run records in the `gozo_ferry` experiment:

- **params:** seed, the knots-to-km/h factor (1.852), the warning threshold, the training window and its size;
- **metrics:** every metric on the frozen holdout (`holdout_recall`, ...);
- **tags:** the git commit, whether the tree was dirty, the SHA-256 of the data and of the holdout, the gate result,
  and the logged model's URI.

`gozo-registry register` refuses a run that failed the gate or came from uncommitted changes: it stays tracked, but
it is never registered. Open the MLflow UI at http://localhost:5000 (from Windows: forward port 5000, or
`ssh -p 2222 -N -L 5000:localhost:5000 malcolmd@127.0.0.1`).

## Serve the champion and roll back (Stage 15)

The image now holds code only (`APP_VERSION` is the code's version). When the API starts, it loads
`models:/gozo_ferry@champion` from the registry in the background:

- `GET /health`: alive (answers at once);
- `GET /ready`: 503 until a model is loaded, then `{"ready": true, "model_version": "gozo_ferry/2", "app_version": "0.6.0"}`;
- `POST /predict` answers 503 until then, and every prediction, and every row in `predictions`, carries the
  registry version that made it.

```bash
make up                       # db, mlflow, api
curl localhost:8888/ready
make champion V=1             # roll back: move the alias, restart the API (no rebuild)
make champion V=2             # and forward again
```

The model card is `docs/model_card.md`; attach it to a version with `gozo-registry card 2 docs/model_card.md`.

## The knowledge layer (Stages 16 and 17)

`data/gozo_operations_2025.csv` logs 77 cancelled crossings in 2025, as staff on duty wrote them: Mġarr is written
six ways, and none of the 14 reasons says whether it is weather. The knowledge in `kg/` says what the words mean:

| File | What it holds |
|---|---|
| `kg/schema.yaml` | Classes (Port, Vessel, Reason, Term, Cancellation), relationships and their cardinalities; the knowledge version |
| `kg/ports.yaml` | The two ports, each with every spelling the log uses |
| `kg/vessels.yaml` | The fleet |
| `kg/reasons.yaml` | The reasons: weather (wind, sea, visibility), technical, operational |
| `kg/synonyms.yaml` | The words staff use in questions |
| `kg/questions.yaml` | The competency questions, with answers worked out by hand |

The decision and the key of a cancellation (date + scheduled time + vessel) are in `docs/adr/0001-knowledge-layer.md`.

```bash
make profile          # how the log writes each port, reason and vessel
make ask SHOW=--show  # each question through the log alone (keyword) and through the knowledge
make kg-load          # build the RDF store kg/build/gozo.nt; run it twice: same triples, same SHA-256
make kg-count         # triples, classes, properties, release and fingerprint
make kg-ask           # the questions in SPARQL
make kg-check         # what make ci runs: build from nothing, load again, same SHA-256, every answer right
make kg-release       # tag kg-v<version> with the store's fingerprint (tests and kg-check first)
```
