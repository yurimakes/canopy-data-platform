import pytest

from mode_inference.model_inference import mode_for_class, model_identity


@pytest.mark.parametrize("value,mode", [(0, "walk"), (1, "bike"), (2, "car"), (3, "bus"), (4, "subway")])
def test_class_mapping(value, mode):
    assert mode_for_class(value) == mode


def test_invalid_class():
    with pytest.raises(ValueError):
        mode_for_class(5)


def test_model_identity():
    assert model_identity("models:/dbw_canopy_dev.ml.canopy_transition_lgbm_pointwise/1") == (
        "dbw_canopy_dev.ml.canopy_transition_lgbm_pointwise", "1"
    )
    assert model_identity("models:/catalog.schema.model@Champion") == (
        "catalog.schema.model", None
    )
