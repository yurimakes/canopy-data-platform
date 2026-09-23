"""Spark schemas for the integrated event and segment streams."""

POINT_STRUCT_DDL = """STRUCT<
event_id: STRING,
user_id: STRING,
trip_id: STRING,
sequence: BIGINT,
event_time: TIMESTAMP,
lat: DOUBLE,
lon: DOUBLE,
predicted_mode: STRING,
confidence: DOUBLE,
model_name: STRING,
model_version: STRING,
predicted_at: TIMESTAMP
>"""

SEGMENT_ACCUMULATOR_STRUCT_DDL = """STRUCT<
user_id: STRING,
mode: STRING,
start_sequence: BIGINT,
end_sequence: BIGINT,
start_time: TIMESTAMP,
end_time: TIMESTAMP,
point_count: BIGINT,
distance_m: DOUBLE,
model_name: STRING,
model_version: STRING,
latest_prediction_at: TIMESTAMP,
last_lat: DOUBLE,
last_lon: DOUBLE
>"""

TRIP_END_STRUCT_DDL = """STRUCT<
event_id: STRING,
trip_id: STRING,
user_id: STRING,
expected_last_sequence: BIGINT,
processing_generation: BIGINT,
parsed_at: TIMESTAMP,
result_owner: STRING
>"""

UNIFIED_EVENT_SCHEMA_DDL = """
event_kind STRING NOT NULL,
event_id STRING NOT NULL,
user_id STRING,
trip_id STRING NOT NULL,
sequence BIGINT,
event_time TIMESTAMP,
lat DOUBLE,
lon DOUBLE,
predicted_mode STRING,
confidence DOUBLE,
model_name STRING,
model_version STRING,
predicted_at TIMESTAMP,
expected_last_sequence BIGINT,
processing_generation BIGINT,
trip_end_parsed_at TIMESTAMP,
result_owner STRING
"""

SEGMENT_OUTPUT_SCHEMA_DDL = """
trip_id STRING NOT NULL,
user_id STRING NOT NULL,
processing_generation BIGINT NOT NULL,
segment_index INT NOT NULL,
segment_id STRING NOT NULL,
mode STRING NOT NULL,
start_sequence BIGINT NOT NULL,
end_sequence BIGINT NOT NULL,
start_time TIMESTAMP NOT NULL,
end_time TIMESTAMP NOT NULL,
point_count BIGINT NOT NULL,
distance_m DOUBLE NOT NULL,
confidence DOUBLE,
model_name STRING NOT NULL,
model_version STRING,
latest_prediction_at TIMESTAMP NOT NULL,
trip_end_parsed_at TIMESTAMP NOT NULL,
segmentation_version STRING NOT NULL,
segmented_at TIMESTAMP NOT NULL
"""

PROCESSOR_STATE_SCHEMA_DDL = f"""
trip_id STRING NOT NULL,
max_gap_seconds INT NOT NULL,
next_sequence BIGINT NOT NULL,
pending ARRAY<{POINT_STRUCT_DDL}> NOT NULL,
fingerprints MAP<BIGINT, STRING> NOT NULL,
raw_window ARRAY<{POINT_STRUCT_DDL}> NOT NULL,
repaired_window ARRAY<STRUCT<point: {POINT_STRUCT_DDL}, mode: STRING>> NOT NULL,
completed_segments ARRAY<{SEGMENT_ACCUMULATOR_STRUCT_DDL}> NOT NULL,
current_segment {SEGMENT_ACCUMULATOR_STRUCT_DDL},
trip_ends ARRAY<{TRIP_END_STRUCT_DDL}> NOT NULL,
ready_generations ARRAY<BIGINT> NOT NULL,
emitted_generations ARRAY<BIGINT> NOT NULL,
sealed_at BIGINT,
conflicted BOOLEAN NOT NULL
"""
