# Validated downstream runtime snapshot

This directory preserves the relative layout required by the tested Canopy
carbon, Final Trip and Weekly modules. SOURCE-MANIFEST.json records the source
hashes at import. It contains source and policy files, not credentials, model
weights or GPS records. Changes to this copy are owned by the downstream bundles.

The original ingestion/inference/segmentation bundles do not import this copy.
The final-trip adapter consumes existing segment predictions and never invokes
LocalModel. Legacy compatibility modules remain available to the shared weekly
domain; this import is not a replacement of upstream inference.

Existing validation evidence: 4 weeks, 12 users, 265 finalized synthetic Trips;
two Azure weekly runs with identical baselines, rankings and behavior metrics;
no second weekly Trip payout. New input adapters require separate contract tests.
