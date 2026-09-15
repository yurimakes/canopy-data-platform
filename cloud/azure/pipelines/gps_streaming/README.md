# GPS streaming first layer

This package defines the stateful core between Silver GPS speed points and the
first-layer segment contract.

Current integration behavior:

- `speed_min_60s` is calculated for `(event_time - 60 s, event_time]` and must
  be persisted with each enriched Silver point.
- The mock detector accepts `speed_min_60s` as part of its input contract but
  deliberately ignores it.
- Each mock segment target is selected uniformly from 200 through 300 derived
  speed points, inclusive.
- The weak mode and confidence are random but replayable for a fixed seed and
  `trip_id`.
- An unfinished trip tail below its random target is not emitted as a closed
  segment. This prevents an ineligible segment from reaching SpeedTransformer.
- Weak output remains metadata and must not be passed into SpeedTransformer as
  a feature or prior.

The core has no Spark dependency. A Databricks adapter can keep one instance of
the state per trip in its stateful operator and write `EnrichedSpeedPoint` and
`SegmentEvent` records to their respective Delta tables. The future real
detector should implement the same `process(DetectorPoint)` boundary.

## Closed-segment inference

`segment_inference.py` defines the bounded handoff to the existing MLflow
pyfunc model:

- The default representative-window policy emits 1 window for 200–249 speed
  points and 3 windows for the mock detector's 250–300 range.
- The first and last eligible portions of longer segments are always covered.
- MLflow receives one pandas row per window in the single `speed_sequence`
  column; every row contains exactly 200 raw km/h values.
- Window probability vectors are averaged, then `argmax` produces the strong
  segment mode. The random weak mode remains output metadata only.
- A segment with fewer than 200 persisted speed points returns
  `insufficient_history` without invoking MLflow. A Databricks adapter should
  treat this as retryable because Delta visibility may lag segment closure.
