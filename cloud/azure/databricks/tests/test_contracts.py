from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_trial_bundle_targets_only_trial_workspace() -> None:
    text = (ROOT / "databricks.yml").read_text()
    assert "dbw_canopy_trial" in text
    assert "CANOPY_TRIAL" in text
    assert "7405612422597045.5" in text
    assert "dbw_canopy_dev" not in text
    assert "CANOPY_DEV" not in text


def test_pipeline_reads_existing_layers_instead_of_event_hubs() -> None:
    text = (ROOT / "segment_generation" / "lakeflow_pipeline.py").read_text()
    assert "read.table(TRIP_ENDED_TABLE)" in text
    assert "read.table(GPS_TABLE)" in text
    assert "read.table(PREDICTIONS_TABLE)" in text
    assert "readStream.format" not in text
    assert "kafka" not in text.lower()


def test_output_contract_has_latency_provenance() -> None:
    text = (ROOT / "segment_generation" / "segmentation.py").read_text()
    for field in (
        "latest_prediction_at",
        "trip_end_parsed_at",
        "segmentation_version",
        "segmented_at",
    ):
        assert field in text
