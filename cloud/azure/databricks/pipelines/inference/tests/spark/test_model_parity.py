from pathlib import Path
import os

import numpy as np
import pandas as pd
import pytest

from mode_inference.contracts import FEATURE_NAMES
from mode_inference.feature_engineering import extract_features
from mode_inference.model_inference import predict_pandas
from tests.helpers import trajectory

pytestmark = pytest.mark.spark

LOCAL_MODEL = Path("/home/aletheia/projects/canopy-transition-model-mlflow/mlruns/1/models/m-64255847b0384df0ab74cc5e12b1cfae/artifacts")


def test_local_mlflow_prediction_matches_native_lightgbm():
    mlflow = pytest.importorskip("mlflow")
    if not LOCAL_MODEL.exists():
        pytest.skip("reference local MLflow artifact is unavailable")
    native = mlflow.lightgbm.load_model(str(LOCAL_MODEL))
    pyfunc = mlflow.pyfunc.load_model(str(LOCAL_MODEL))
    frame = pd.DataFrame(extract_features(trajectory(count=80))).loc[
        [0, 1, 4, 9, 29, 59, 79], list(FEATURE_NAMES)
    ]
    expected = native.predict(frame).astype(int)
    actual = np.asarray(predict_pandas(pyfunc, frame)).astype(int)
    np.testing.assert_array_equal(actual, expected)


@pytest.mark.registered_model
def test_registered_model_matches_pinned_local_artifact():
    model_uri = os.getenv("CANOPY_REGISTERED_MODEL_URI")
    if not model_uri:
        pytest.skip("CANOPY_REGISTERED_MODEL_URI is not configured")
    mlflow = pytest.importorskip("mlflow")
    if not LOCAL_MODEL.exists():
        pytest.skip("reference local MLflow artifact is unavailable")
    mlflow.set_tracking_uri("databricks://CANOPY_DEV")
    mlflow.set_registry_uri("databricks-uc://CANOPY_DEV")
    local_model = mlflow.pyfunc.load_model(str(LOCAL_MODEL))
    registered_model = mlflow.pyfunc.load_model(model_uri)
    frame = pd.DataFrame(extract_features(trajectory(count=80))).loc[
        [0, 1, 4, 9, 29, 59, 79], list(FEATURE_NAMES)
    ]
    local_prediction = np.asarray(predict_pandas(local_model, frame)).astype(int)
    registered_prediction = np.asarray(predict_pandas(registered_model, frame)).astype(int)
    np.testing.assert_array_equal(registered_prediction, local_prediction)
