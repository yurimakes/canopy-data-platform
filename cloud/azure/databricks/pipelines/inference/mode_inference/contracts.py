"""Stable feature, state, and public-output contracts."""

FEATURE_NAMES = (
    "speed",
    "acceleration",
    "distance",
    "bearing_change",
    "speed_mean_5",
    "speed_std_5",
    "speed_max_10",
    "speed_mean_30",
    "speed_std_30",
    "speed_max_60",
    "speed_mean_150",
    "stop_count_60",
    "stop_count_150",
    "stoppage_ratio_60",
    "speed_q25_60",
    "speed_q75_60",
    "accel_std_30",
)

MODE_BY_CLASS = {0: "walk", 1: "bike", 2: "car", 3: "bus", 4: "subway"}
MAX_RAW_POINTS = 151

FEATURE_OUTPUT_SCHEMA_DDL = """
event_id STRING NOT NULL,
user_id STRING NOT NULL,
trip_id STRING NOT NULL,
sequence BIGINT NOT NULL,
event_time TIMESTAMP NOT NULL,
processor_entered_at TIMESTAMP NOT NULL,
feature_compute_started_at TIMESTAMP NOT NULL,
features_processed_at TIMESTAMP NOT NULL,
speed DOUBLE NOT NULL,
acceleration DOUBLE NOT NULL,
distance DOUBLE NOT NULL,
bearing_change DOUBLE NOT NULL,
speed_mean_5 DOUBLE NOT NULL,
speed_std_5 DOUBLE NOT NULL,
speed_max_10 DOUBLE NOT NULL,
speed_mean_30 DOUBLE NOT NULL,
speed_std_30 DOUBLE NOT NULL,
speed_max_60 DOUBLE NOT NULL,
speed_mean_150 DOUBLE NOT NULL,
stop_count_60 DOUBLE NOT NULL,
stop_count_150 DOUBLE NOT NULL,
stoppage_ratio_60 DOUBLE NOT NULL,
speed_q25_60 DOUBLE NOT NULL,
speed_q75_60 DOUBLE NOT NULL,
accel_std_30 DOUBLE NOT NULL
"""

MODE_PREDICTIONS_SCHEMA_DDL = """
event_id STRING NOT NULL,
user_id STRING NOT NULL,
trip_id STRING NOT NULL,
sequence BIGINT NOT NULL,
event_time TIMESTAMP NOT NULL,
predicted_class INT NOT NULL,
predicted_mode STRING NOT NULL,
confidence DOUBLE,
model_name STRING NOT NULL,
model_version STRING,
processor_entered_at TIMESTAMP NOT NULL,
feature_compute_started_at TIMESTAMP NOT NULL,
features_processed_at TIMESTAMP NOT NULL,
predicted_at TIMESTAMP NOT NULL
"""
