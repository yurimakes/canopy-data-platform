from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bundle_is_trial_baseline_only() -> None:
    bundle = (ROOT / "databricks.yml").read_text()
    assert "dbw_canopy_trial" in bundle
    assert "CANOPY_TRIAL" in bundle
    assert "7405612422597045.5" in bundle
    assert "silver_schema" in bundle
    assert "gps_observations" in bundle
    assert "trip_ended_events" in bundle
    assert "mode_segments" in bundle
    assert "replay_" not in bundle
    assert "silver_mode_predictions" not in bundle


def test_baseline_pipeline_uses_configurable_trigger_and_expected_state_guards() -> None:
    resource = (
        ROOT / "resources" / "integrated_mode_segmentation.baseline.pipeline.yml"
    ).read_text()
    assert "pipelines.trigger.interval: ${var.baseline_trigger_interval}" in resource
    assert "canopy.state_timeout: ${var.state_timeout}" in resource
    assert "canopy.state_store_partitions: ${var.state_store_partitions}" in resource
    assert "canopy.max_repair_gap_seconds: ${var.max_repair_gap_seconds}" in resource


def test_bundle_packages_internal_mode_inference_library() -> None:
    bundle = (ROOT / "databricks.yml").read_text()
    project = (ROOT / "pyproject.toml").read_text()
    resource = (
        ROOT / "resources" / "integrated_mode_segmentation.baseline.pipeline.yml"
    ).read_text()
    assert "artifacts:" in bundle and "type: whl" in bundle
    assert 'packages = ["integrated_mode_segmentation", "mode_inference"]' in project
    assert "../inference/mode_inference" not in project
    assert (ROOT / "mode_inference" / "state.py").exists()
    assert "canopy_integrated_mode_segmentation-0.1.0-py3-none-any.whl" in resource


def test_critical_output_path_is_native_streaming() -> None:
    pipeline = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "@dp.table(" in pipeline
    assert "stateful_segment_rows" in pipeline
    assert "foreachBatch" not in pipeline
