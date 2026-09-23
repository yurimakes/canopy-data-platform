"""Canonical Mission Profile Gold projection for the Weekly pipeline."""

from __future__ import annotations

from pyspark.sql import DataFrame, functions as F


PROFILE_COLUMNS = (
    ("type", "string"),
    ("profile_version", "string"),
    ("profile_status", "string"),
    ("user_id", "string"),
    ("campaign_id", "string"),
    ("source_week_start", "string"),
    ("source_week_end", "string"),
    ("effective_week_start", "string"),
    ("valid_trip_count", "int"),
    ("invalid_trip_count", "int"),
    ("invalid_trip_reasons", "map<string,int>"),
    ("car_primary_trip_count", "int"),
    ("car_ratio", "double"),
    ("short_car_trip_count", "int"),
    ("short_car_share", "double"),
    ("transit_primary_trip_count", "int"),
    ("low_carbon_trip_count", "int"),
    ("carbon_change_rate", "double"),
    ("mission_history_source", "string"),
    ("preference_positive_evidence_count", "int"),
    ("category_preferences_json", "string"),
    ("difficulty_state_json", "string"),
    ("family_capability_json", "string"),
    ("profile_hash", "string"),
)


def build_weekly_user_profile(profile_df: DataFrame) -> DataFrame:
    """Return canonical Mission Profile Gold in the Lakeflow schema order."""

    missing = [name for name, _ in PROFILE_COLUMNS if name not in profile_df.columns]
    if missing:
        raise ValueError(
            "Mission Profile Gold is missing required columns: "
            + ", ".join(missing)
        )

    return profile_df.select(
        *[
            F.col(name).cast(data_type).alias(name)
            for name, data_type in PROFILE_COLUMNS
        ]
    )
