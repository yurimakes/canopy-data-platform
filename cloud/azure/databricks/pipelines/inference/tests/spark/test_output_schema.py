import shutil

import pytest

pytestmark = pytest.mark.spark


def test_feature_output_schema_is_accepted_by_spark():
    pytest.importorskip("pyspark")
    if shutil.which("java") is None:
        pytest.skip("local Spark JVM is unavailable: java not found")
    from pyspark.sql import SparkSession
    from pyspark.sql.types import StructType
    from mode_inference.contracts import FEATURE_OUTPUT_SCHEMA_DDL, FEATURE_NAMES

    spark = SparkSession.builder.master("local[1]").appName("pipeline-b-schema-test").getOrCreate()
    try:
        schema = StructType.fromDDL(FEATURE_OUTPUT_SCHEMA_DDL)
        assert [field.name for field in schema.fields][10:] == list(FEATURE_NAMES)
        assert [field.name for field in schema.fields][8:10] == ["lat", "lon"]
        assert all(not field.nullable for field in schema.fields)
    finally:
        spark.stop()
