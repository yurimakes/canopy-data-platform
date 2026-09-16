"""Weekly Lakeflow graph only. All placeholders are empty, not calculated results.

Replace each function with its owner's DataFrame transformation later.
Do not call Cosmos, start Jobs, or perform writes inside dataset definitions.
The scaffold columns are NOT the team's final business schema.
"""
from pyspark import pipelines as dp
from pyspark.sql import SparkSession, functions as F

spark = SparkSession.builder.getOrCreate()
SCAFFOLD_SCHEMA = "_scaffold_stage string, _implementation_status string"
SCAFFOLD_PROPERTIES = {"canopy.implementation_status": "scaffold"}


def pending(stage, *parents):
    """Declare upstream dependencies without fabricating any business records."""
    frame = spark.read.table(parents[0])
    for parent in parents[1:]:
        frame = frame.unionByName(spark.read.table(parent))
    return frame.limit(0).select(F.lit(stage).alias("_scaffold_stage"),
                                 F.lit("not_implemented").alias("_implementation_status"))


@dp.temporary_view(comment="TODO: read Final Trip Gold from ADLS; never Cosmos.")
def final_trip_gold_input():
    # Final Trip location, week boundaries and the business schema are connected later.
    return spark.createDataFrame([], SCAFFOLD_SCHEMA)


@dp.temporary_view(comment="TODO: aggregate Final Trips by campaign/user/week.")
def weekly_summary():
    return pending("weekly_summary", "final_trip_gold_input")


@dp.materialized_view(comment="Weekly Gold storage placeholder.", table_properties=SCAFFOLD_PROPERTIES)
def weekly_gold():
    return pending("weekly_gold", "weekly_summary")


@dp.temporary_view(comment="TODO: apply Baseline Eligibility policy.")
def baseline_eligibility():
    return pending("baseline_eligibility", "weekly_gold")


@dp.temporary_view(comment="TODO: calculate/update Personal Baseline, including prior snapshots.")
def personal_baseline():
    return pending("personal_baseline", "baseline_eligibility")


@dp.temporary_view(comment="TODO: retain Personal-ready users.")
def personal_ready_users():
    return pending("personal_ready_users", "personal_baseline")


@dp.temporary_view(comment="TODO: apply Global Eligibility policy.")
def global_eligibility():
    return pending("global_eligibility", "personal_ready_users")


@dp.temporary_view(comment="TODO: calculate/update Global Baseline, including prior snapshots.")
def global_baseline():
    return pending("global_baseline", "global_eligibility")


@dp.materialized_view(comment="Baseline Gold storage placeholder.", table_properties=SCAFFOLD_PROPERTIES)
def baseline_gold():
    return pending("baseline_gold", "personal_baseline", "global_baseline")


@dp.temporary_view(comment="TODO: compare this week's data with eligible baselines.")
def behavior_change():
    return pending("behavior_change", "weekly_gold", "baseline_gold")


@dp.temporary_view(comment="TODO: assemble Weekly User Profile.")
def weekly_user_profile():
    return pending("weekly_user_profile", "weekly_gold", "behavior_change")


@dp.materialized_view(comment="TODO: select next week's missions.", table_properties=SCAFFOLD_PROPERTIES)
def next_week_missions():
    return pending("next_week_missions", "weekly_user_profile")


@dp.materialized_view(comment="TODO: aggregate ranking from weekly profiles.", table_properties=SCAFFOLD_PROPERTIES)
def ranking():
    return pending("ranking", "weekly_user_profile")


@dp.materialized_view(comment="TODO: aggregate Campaign KPI from weekly profiles.", table_properties=SCAFFOLD_PROPERTIES)
def campaign_kpi():
    return pending("campaign_kpi", "weekly_user_profile", "weekly_gold")


@dp.materialized_view(comment="ADLS Gold output boundary; final projection contract is not implemented.",
                      table_properties=SCAFFOLD_PROPERTIES)
def weekly_outputs_gold():
    return pending("weekly_outputs_gold", "weekly_gold", "baseline_gold", "weekly_user_profile",
                   "next_week_missions", "ranking", "campaign_kpi")
