SPARK VALIDATION RESULT

## 1. Environment

- Workspace: existing `dbw-canopy-dev` development workspace, profile `CANOPY_DEV`.
- Compute: Databricks serverless environment `client 1`. The serverless job did not expose a Databricks Runtime label; the observed Spark version was `4.2.0`.
- Python: `3.10.12`.
- Spark SQL session timezone: explicitly set to `UTC` and verified as `UTC`.
- Final successful parent run: `1084822153507913`; task run: `21813718444973`.
- The workspace accepts only serverless compute. An initial classic-cluster submission was rejected before creating a run with `Only serverless compute is supported in the workspace.`

## 2. Tests executed

Local checks:

```bash
python3 -m compileall -q gps_ingestion tests
python3 -m unittest discover -s tests/unit -v
git diff --check
```

Databricks invocation:

```bash
databricks jobs submit --json @/tmp/canopy_pipeline_a_spark_job.json --profile CANOPY_DEV
```

The one-time serverless task ran a temporary Python runner from an isolated workspace folder. It used `unittest` discovery for `tests/unit` and `tests/spark`. The runner reused the Databricks-managed Spark session and adapted only the dedup test storage paths from driver-local `/tmp` to a temporary managed volume; test inputs and assertions were unchanged.

## 3. Results

- Spark parser/projection/deduplication suite: **PASS** — 18 run, 18 passed, 0 failures, 0 errors, 0 skipped (`42.799s`).
- Unit suite in Databricks: **PASS** — 12 run, 12 passed, 0 failures, 0 errors, 0 skipped (`0.114s`).
- Unit suite locally: **PASS** — 12 run, 12 passed, 0 failures, 0 errors, 0 skipped.
- Compile check: **PASS**.
- `git diff --check`: **PASS**.

The successful Spark run covered Bronze projection, VARIANT parsing and type inspection, required-key versus explicit-null handling, v0.1/v0.2 validation, rejection taxonomy, observations projection, quarantine projection, bounded `event_id` deduplication, and the `event_hub_enqueued_at` watermark choice.

## 4. Runtime/API compatibility

- `try_parse_json`, `try_variant_get`, `schema_of_variant`, and `is_variant_null` work as Spark SQL expressions on Spark 4.2.0. Their `pyspark.sql.functions` wrappers are absent in this serverless Spark Connect client.
- `array_compact` is available through `pyspark.sql.functions` and behaved as expected.
- `dropDuplicatesWithinWatermark(["event_id"])` executed successfully in both dedup tests with a `1 day` watermark on `event_hub_enqueued_at`.
- VARIANT probing returned `OBJECT<a: VOID, b: ARRAY<BIGINT>>`, distinguished explicit JSON null, and extracted typed arrays correctly.
- UTC timestamp probing converted `2026-09-16T01:02:03.123Z` to `2026-09-16 01:02:03.123000` under the UTC session timezone.

## 5. Failures and fixes

Two production compatibility defects were found and fixed in `gps_ingestion/spark_ingestion.py`:

1. Calls to absent Spark Connect Python wrappers raised attribute errors before query execution. The VARIANT functions now use their supported Spark SQL expressions through `F.expr`.
2. Spark 4 ANSI behavior made `element_at(rejection_reasons, 1)` throw for a valid event's empty reason array. It now uses `try_element_at`, yielding the required null primary reason.

Serverless test-environment issues were diagnosed separately:

- The repository dedup tests' driver-local `/tmp` paths resolved to disabled public DBFS (`DBFS_DISABLED`).
- Serverless disallowed implicit checkpoints, workspace-file state stores, local-file checkpoints, and overriding the checkpoint file manager.
- The final run used the temporary managed volume `dbw_canopy_dev.default.codex_pipeline_a_spark_validation_20260916_1` only for synthetic Parquet input and isolated test checkpoints. The volume and temporary workspace folder were deleted after the successful run and their absence was verified.

No tests or architecture were changed in the repository.

## 6. Git status

- Branch: `fix/pipeline-a-spark-validation`.
- Source fix commit: `679547a` (`fix: support Spark Connect variant validation`).
- Source file changed: `gps_ingestion/spark_ingestion.py`, solely for Spark Connect VARIANT function access and Spark 4 safe empty-array handling.
- The required handoff report is committed separately after the source fix; final worktree status is clean.

## 7. Deployment readiness assessment

Pipeline A's synthetic Spark parser/projection tests and stateful deduplication tests pass on Databricks serverless Spark 4.2.0. The runtime behavior required by the current implementation is supported with the committed compatibility fix.

No Event Hubs access occurred. No secrets were accessed. `gps_ingestion/lakeflow_pipeline.py` was not executed. No Unity Catalog table was created, overwritten, or queried. No deployment, pipeline update, or existing checkpoint/resource state change occurred. No existing pipeline was started or stopped.
