import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_reuses_inference_and_keeps_public_prediction_contract() -> None:
    text = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "stateful_feature_rows" in text
    assert "infer_enriched_predictions" in text
    assert "public_predictions" in text
    assert "MODE_PREDICTIONS_SCHEMA_DDL" in text


def test_pipeline_uses_tagged_union_and_native_stateful_segment_output() -> None:
    text = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "unified_events" in text
    assert "stateful_segment_rows" in text
    assert "readStream.table" in text
    assert "foreachBatch" not in text
    assert ".join(" not in text


def test_prediction_and_segment_tables_have_distinct_pipeline_owners() -> None:
    text = (ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py").read_text()
    assert "OUTPUT_PREDICTIONS_TABLE" in text
    assert "OUTPUT_SEGMENTS_TABLE" in text
    assert text.count("@dp.table(") == 2


def test_temporary_view_uses_only_supported_pyspark_decorator_arguments() -> None:
    path = ROOT / "integrated_mode_segmentation" / "lakeflow_pipeline.py"
    tree = ast.parse(path.read_text())
    decorators = [
        decorator
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "temporary_view"
    ]
    assert len(decorators) == 1
    assert {keyword.arg for keyword in decorators[0].keywords} <= {
        "name",
        "comment",
        "spark_conf",
    }
