# Complete payload

Experimental downstream finalization boundary for the new sandbox path.

Input:

```text
dbw_canopy_trial.sandbox.jun_016_silver_gps_observations
dbw_canopy_trial.sandbox.jun_016_gold_mode_detection_results
```

Output:

```text
dbw_canopy_trial.sandbox.jun_016_gold_complete_payloads
```

The first slice is intentionally one-shot by `trip_id`. It derives measured
segment distance from ordered GPS legs, applies the current carbon-policy-v1
factors, builds the durable JSON payload, and MERGEs by trip/user/generation.

Deploy:

```bash
databricks bundle deploy -t sandbox --profile CANOPY_TRIAL
```

Run:

```bash
databricks bundle run -t sandbox \
  --params trip_id=<TRIP_ID> \
  complete_payload_finalize \
  --profile CANOPY_TRIAL
```

Cosmos projection is deliberately not part of this slice. The durable Gold
payload is the handoff boundary for the next step.
