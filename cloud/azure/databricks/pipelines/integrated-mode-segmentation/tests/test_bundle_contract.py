from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bundle_is_trial_only_and_owns_separate_replay_tables() -> None:
    bundle = (ROOT / "databricks.yml").read_text()
    assert "dbw_canopy_trial" in bundle
    assert "CANOPY_TRIAL" in bundle
    assert "7405612422597045.5" in bundle
    assert "replay_integrated_mode_predictions" in bundle
    assert "replay_integrated_mode_segments" in bundle
    assert "silver_mode_predictions" not in bundle
    assert "silver_mode_segments" not in bundle


def test_pipeline_uses_one_second_trigger_and_expected_state_guards() -> None:
    resource = (
        ROOT / "resources" / "integrated_mode_segmentation.replay.pipeline.yml"
    ).read_text()
    assert 'pipelines.trigger.interval: "1 second"' in resource
    assert "canopy.state_timeout: ${var.state_timeout}" in resource
    assert "canopy.state_store_partitions: ${var.state_store_partitions}" in resource
    assert "canopy.max_repair_gap_seconds: ${var.max_repair_gap_seconds}" in resource


def test_bundle_builds_shared_wheel_instead_of_copying_inference_source() -> None:
    bundle = (ROOT / "databricks.yml").read_text()
    project = (ROOT / "pyproject.toml").read_text()
    resource = (
        ROOT / "resources" / "integrated_mode_segmentation.replay.pipeline.yml"
    ).read_text()
    assert "artifacts:" in bundle and "type: whl" in bundle
    assert '../inference/mode_inference' in project
    assert "- whl:" in resource
    assert not (ROOT / "integrated_mode_segmentation" / "mode_inference").exists()


def test_critical_output_path_is_native_streaming() -> None:
    pipeline = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "@dp.table(" in pipeline
    assert "stateful_segment_rows" in pipeline
    assert "foreachBatch" not in pipeline
