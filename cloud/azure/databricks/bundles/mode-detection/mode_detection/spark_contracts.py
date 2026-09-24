"""Spark schemas for the mode-detection stateful boundary."""

UNIFIED_EVENT_SCHEMA_DDL = """
event_kind STRING NOT NULL,
event_id STRING NOT NULL,
trip_id STRING NOT NULL,
user_id STRING,
sequence BIGINT,
event_time TIMESTAMP,
lat DOUBLE,
lon DOUBLE,
accuracy DOUBLE,
altitude_m DOUBLE,
campaign_id STRING,
started_at TIMESTAMP,
ended_at TIMESTAMP,
expected_last_sequence BIGINT,
occurred_at TIMESTAMP,
processing_generation BIGINT,
result_owner STRING
"""

FINAL_SEGMENT_STRUCT_DDL = """STRUCT<
segment_id: STRING,
mode: STRING,
model_prediction: STRING,
start_time: STRING,
end_time: STRING,
distance_m: DOUBLE,
confidence: DOUBLE,
prediction_count: BIGINT,
carbon_kg: DOUBLE
>"""

CARBON_STRUCT_DDL = """STRUCT<
kg_co2e: DOUBLE,
policy_version: STRING,
factor_version: STRING,
unit: STRING,
mode_source: STRING,
user_confirmation_applied: BOOLEAN
>"""

COMPLETE_PAYLOAD_SCHEMA_DDL = f"""
trip_id STRING NOT NULL,
user_id STRING NOT NULL,
campaign_id STRING NOT NULL,
status STRING NOT NULL,
mode_detection_status STRING NOT NULL,
mode_detection_reason STRING,
started_at STRING NOT NULL,
ended_at STRING NOT NULL,
updated_at STRING NOT NULL,
processing_generation BIGINT NOT NULL,
expected_last_sequence BIGINT NOT NULL,
segments ARRAY<{FINAL_SEGMENT_STRUCT_DDL}> NOT NULL,
model_name STRING NOT NULL,
model_version STRING NOT NULL,
feature_version STRING NOT NULL,
total_distance_m DOUBLE NOT NULL,
carbon {CARBON_STRUCT_DDL} NOT NULL,
finalization_hash STRING NOT NULL,
sealed_at TIMESTAMP NOT NULL,
document_json STRING NOT NULL
"""

PROCESSOR_STATE_SCHEMA_DDL = """
payload STRING NOT NULL
"""
