# Sandbox replay fixtures

Portable OD-derived canonical GPS fixtures for end-to-end testing of the Canopy sandbox pipeline.

Source provenance:

- repository: `aletheia-ops/od-audit`
- branch: `main`
- squash commit: `bd93679520b2a913fc687d0d5984ee2ee4fc2f99`
- source directory: `sandbox-replay-fixtures/`

The fixtures preserve selected original GPS observations and event-time cadence; they are not resampled to 1 Hz. Elapsed duration therefore does not equal GPS row count.

## Validate

```bash
python tools/sandbox-replay/tools/validate_corpus.py tools/sandbox-replay
```

## Install sender dependency

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e tools/sandbox-replay
```

Create a repo-local `.env` from the committed example:

```bash
cp tools/sandbox-replay/.env.example .env
```

Then set the connection string in `.env`:

```dotenv
EVENT_HUB_CONNECTION_STRING=...
EVENT_HUB_NAME=evh-canopy-sandbox-5dt016
```

The sender automatically loads the repository-root `.env`. The actual connection string is never committed. If `EVENT_HUB_NAME` is omitted, the sender defaults to `evh-canopy-sandbox-5dt016`.

## Replay residual-tail fixture

```bash
python tools/sandbox-replay/tools/publish_eventhub.py \
  --trip tools/sandbox-replay/trips/residual_tail_723s \
  --replay-cadence-ms 0
```

Arbitrary cutoff:

```bash
python tools/sandbox-replay/tools/publish_eventhub.py \
  --trip tools/sandbox-replay/trips/residual_tail_723s \
  --duration-seconds 610 \
  --replay-cadence-ms 0
```

The cutoff selects the last real GPS observation at or before the requested elapsed duration and does not synthesize a point.

## Current sandbox path

```text
evhns-canopy-dev / evh-canopy-sandbox-5dt016
    ↓ consumer group canopy-sandbox-testline
5dt016-generic-event-ingestion-sandbox-testline
    ↓
dbw_canopy_trial.sandbox.jun_016_silver_gps_observations
dbw_canopy_trial.sandbox.jun_016_silver_trip_ended_events
    ↓
5dt016-mode-detection-sandbox
    ↓
dbw_canopy_trial.sandbox.jun_016_gold_mode_detection_results
```

Keep continuous wrapper jobs `PAUSED` in source control.
