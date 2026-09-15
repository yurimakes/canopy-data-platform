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
