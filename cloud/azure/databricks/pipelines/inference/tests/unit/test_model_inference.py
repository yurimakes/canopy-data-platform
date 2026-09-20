import inspect

import pytest

from mode_inference.model_inference import (
    infer_enriched_predictions,
    infer_predictions,
    mode_for_class,
    model_identity,
    public_predictions,
)


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


def test_public_and_enriched_prediction_projections_are_separate_contracts():
    enriched_source = inspect.getsource(infer_enriched_predictions)
    public_source = inspect.getsource(public_predictions)
    compatibility_source = inspect.getsource(infer_predictions)

    assert '"lat"' in enriched_source and '"lon"' in enriched_source
    assert '"lat"' not in public_source and '"lon"' not in public_source
    assert "infer_enriched_predictions" in compatibility_source
    assert "public_predictions" in compatibility_source
