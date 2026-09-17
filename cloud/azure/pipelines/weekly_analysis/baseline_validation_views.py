"""Temporary materialized views for validating Personal/Global Baseline.

These views expose pipeline-internal temporary views so their actual row counts
and values can be inspected during Databricks development validation.

Remove or stop registering this file after validation is complete.
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()


@dp.materialized_view(
    comment="검증용: Personal Baseline 실제 계산 결과 확인"
)
def debug_personal_baseline():
    return spark.read.table("personal_baseline")


@dp.materialized_view(
    comment="검증용: Global 계산 대상 Personal ready 사용자 확인"
)
def debug_personal_ready_users():
    return spark.read.table("personal_ready_users")


@dp.materialized_view(
    comment="검증용: Global Eligibility 실제 판정 결과 확인"
)
def debug_global_eligibility():
    return spark.read.table("global_eligibility")


@dp.materialized_view(
    comment="검증용: Global Baseline 실제 계산 결과 확인"
)
def debug_global_baseline():
    return spark.read.table("global_baseline")