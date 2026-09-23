DEDUPLICATION DEFAULT FIX

## 1. Changes

Changed the configurable development default for `deduplication_watermark` from
`7 days` to `1 day`.

Files changed for the correction:

- `databricks.yml`
- `README.md`
- `codex_pipeline_a_implementation.md`

This handoff adds `codex_pipeline_a_dedup_fix.md`. The architecture is unchanged:
the key remains `event_id`, the watermark column remains
`event_hub_enqueued_at`, and the guarantee remains bounded deduplication rather
than permanent global uniqueness.

## 2. Validation

- `python3 -m compileall -q gps_ingestion tests`: passed with exit code 0.
- `python3 -m unittest discover -s tests/unit -v`: 12 tests passed; `OK`.
- `git diff --check`: passed with no output.
- `databricks bundle validate --profile CANOPY_DEV -t dev`: exit code 0;
  `Validation OK!` for bundle `canopy-gps-streaming`, target `dev`.
- Spark tests were not rerun because the correction does not affect Spark code
  and the optional local PySpark dependency remains unavailable.

No deploy, pipeline start, Event Hubs consumption, or resource mutation occurred.

## 3. Git commit

Correction commit:

```text
4b51dc21b9926a6a525bd7fc25536a6d1e87369e
chore: tune ingestion deduplication default
```

This handoff file is committed separately so it can cite the immutable correction
commit. Nothing was pushed.

## 4. Final status

- Development default: `1 day`.
- Deduplication remains configurable and operationally tunable.
- Branch: `feature/pipeline-a-cleanup`.
- Final worktree status after the handoff commit: clean.
