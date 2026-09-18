#!/usr/bin/env bash
set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-CANOPY_DEV}"
SOURCE="dbfs:/databricks/mlflow-tracking/2664034343403002/logged_models/m-9a3d06908cfb4e7a90ae76e490a83636/artifacts/model.skops"
DEST="mode_inference/artifacts/transition_lgbm_v1/model.skops"

mkdir -p "$(dirname "$DEST")"

databricks fs cp "$SOURCE" "$DEST" --profile "$PROFILE" --overwrite

echo "Fetched:"
echo "  $SOURCE"
echo "-> $DEST"
ls -lh "$DEST"
