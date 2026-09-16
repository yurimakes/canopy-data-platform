import pytest

from mode_inference.configuration import ModeInferenceConfig


def test_development_defaults_own_only_predictions():
    config = ModeInferenceConfig()
    assert config.input_table == "dbw_canopy_dev.silver.gps_observations"
    assert config.output_table == "dbw_canopy_dev.silver.mode_predictions"
    assert config.model_uri.endswith("/1")


@pytest.mark.parametrize("field", ["catalog", "silver_schema", "input_observations_name", "output_predictions_name"])
def test_invalid_identifier(field):
    values = {field: "bad-name"}
    with pytest.raises(ValueError):
        ModeInferenceConfig(**values)


def test_rejects_reserved_schema_and_unsupported_timeout():
    with pytest.raises(ValueError, match="reserved"):
        ModeInferenceConfig(silver_schema="information_schema")
    with pytest.raises(ValueError, match="state_timeout"):
        ModeInferenceConfig(state_timeout="7 days")
