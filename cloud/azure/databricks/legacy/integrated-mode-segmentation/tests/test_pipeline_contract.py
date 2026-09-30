from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_reuses_inference_without_public_prediction_sink() -> None:
    text = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "stateful_feature_rows" in text
    assert "infer_enriched_predictions" in text
    assert "public_predictions" not in text
    assert "OUTPUT_PREDICTIONS_TABLE" not in text
    assert "OUTPUT_ENRICHED_PREDICTIONS_TABLE" not in text


def test_pipeline_uses_tagged_union_and_native_stateful_segment_output() -> None:
    text = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "unified_events" in text
    assert "stateful_segment_rows" in text
    assert "readStream.table" in text
    assert "foreachBatch" not in text
    assert ".join(" not in text


def test_pipeline_has_one_public_streaming_sink() -> None:
    text = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "OUTPUT_SEGMENTS_TABLE" in text
    assert "OUTPUT_SEGMENTS_FQN" in text
    assert text.count("@dp.table(") == 1
    assert "silver_integrated_mode_segments" not in text


def test_inference_flows_directly_into_segmentation() -> None:
    text = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "predictions = infer_enriched_predictions(" in text
    assert "events = unified_events(predictions, trip_ends)" in text
    assert "return stateful_segment_rows(" in text
