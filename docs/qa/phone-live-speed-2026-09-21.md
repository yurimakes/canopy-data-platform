# Phone speed, live prediction and latency fixes

## Changes

- Build 8 shows current device speed in km/h. Invalid, inaccurate (>50 m), future or >15-second-old GPS fixes show waiting rather than a false zero.
- The movement panel always retains a labelled 48-point-minimum-height collapse/expand control outside the map. Collapsed content retains duration, distance, speed and current mode. Starting a new Trip expands it again.
- Production polls the existing authenticated owner-scoped Trip endpoint for `live_prediction`, with no overlapping requests or resets on each GPS event. Predictions expire after 30 seconds; provisional display never changes final segments or rewards.
- Azure API adds this field to its public response. The deployed package changes only `services/trip_service.py` and the release marker; other deployed modules are preserved.
- Databricks changes live in the separate pipeline repository, under `pipelines/personal-stack/service/`. Original imported source/model/reference files remain unchanged.

## Why prior behavior differed

Main integration had removed cloud live prediction polling. The original cloud worker inferred only after Stop; the local server's `/predictions` route was never implemented in the cloud API. Matching checkpoint files did not reproduce live display.

Measured actual phone worker time before this change was 19.092 and 22.984 seconds: GPS read/wait 12.920 / 17.482 s, inference/transit 0.780 / 0.258 s, Gold write/readback 4.548 / 4.436 s, Cosmos 0.056 / 0.057 s. These are server timings, not button-to-screen measurements. Earlier 90-second behavior also involved Event Hub send failures followed by minute-timer recovery; bounded producer retry was already deployed separately.

The GPS pipeline now requests a one-second trigger interval instead of default scheduling. This is not a one-second end-to-end latency claim. Personal and main have different Functions hosting/Python and Cosmos capacity models; those differences alone were not proven to cause the observed delay.

## Walking misclassification

The 29-event real phone input contained coordinate jitter: a point with device speed ~4.4 km/h had coordinate-derived speed ~25 km/h. Silver contained `raw_speed`, but the original batch reader dropped it. Short windows repeated the last speed to fill 200 samples.

The service adapter retains device speed, converts m/s to km/h, and uses the existing model architecture's padding mask. Where device speeds are available, missing-speed intervals remain explicitly partial. Original weights, scaler, label encoder and transit references are unchanged. Completely sensorless records use a separately versioned coordinate fallback; this is a remaining accuracy limitation, not proof of correct classification.

Read-only replay of the reported all-walking Trip produced walking at 0.918 confidence for the usable measured-speed section (48.2 m), with missing-speed start intervals marked partial. The original 115.6 m result included GPS jitter. This is not a claim about ground-truth distance, calibrated confidence, or accuracy across other transport modes. Existing user history and rewards were not rewritten.

## Validation

- TypeScript type check and eight speed/geometry tests passed.
- 36 existing Trip API/lifecycle/dispatch tests and two live-field ownership tests passed.
- Pipeline adapter tests cover device units, invalid speeds, padding masks, full windows, stale updates and Stop concurrency.
- All 261 archived runtime/model/reference hashes verified unchanged.
- Initial live tests exposed an unsupported Spark Connect `newSession` call and a collecting-Trip query that incorrectly required a field set only at Stop. Both were fixed and the failed fixtures were stopped. These attempts are not counted as successful acceptance runs.
- Build 8 (`17cb9fa1-cdd0-4409-90b8-4766c8b3762b`) and Apple submission (`be606596-0787-42e7-9ec2-535b4b011b74`) completed. Apple availability in TestFlight and physical iPhone interaction are separate checks.

## Final warm-server acceptance

Original personal Azure logs (`ready-359e82327a`) measured Stop-to-API-result at 27.994 and 22.796 s, not under ten seconds. Main after producer retry measured 27.203 / 27.265 s. These must not be confused with local model execution time.

Trigger tuning alone plus live display measured 30.375 / 19.484 s; direct ingestion alone measured 34.266 / 24.906 s. Neither established a reliable improvement. The final configuration uses four shuffle/state partitions on the verified DBR 18.3 pipeline, preserving checkpoints through supported state repartitioning. See the [Azure Databricks state repartitioning reference](https://learn.microsoft.com/azure/databricks/structured-streaming/state-repartitioning).

Final two synthetic walking Trips through the normal Azure HTTP API:

|Measurement|Trip 1|Trip 2|
|---|---:|---:|
|Stop request to API result|10.766 s|13.922 s|
|GPS read/wait|3.569 s|6.762 s|
|Model and transit|0.525 s|0.530 s|
|Gold write/readback|4.091 s|4.174 s|
|Cosmos publish|0.059 s|0.056 s|
|Final mode|walk|walk|
|Live observations returned before Stop|4|6|

Both completed normally; comparison re-read preserved the same reward record and points (zero-point short fixtures), and authenticated history/community queries passed. This is not positive paid-reward or multi-week regression evidence. Eleven pipeline service tests passed. Evidence is in the pipeline repository at `pipelines/personal-stack/evidence/phone-live-2026-09-21.json`.

These timings include HTTP Stop/polling but exclude physical iPhone LTE/background behavior. They are two warm-server samples, not a latency SLA, and do not guarantee sub-ten-second results. Build 8 is uploaded; actual on-device layout, collapse/expand and movement tests still require installing that build.
