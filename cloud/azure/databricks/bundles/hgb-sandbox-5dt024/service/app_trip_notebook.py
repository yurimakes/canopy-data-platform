# Databricks notebook source
import sys, json
dbutils.widgets.text("bundle_root", "")
root = dbutils.widgets.get("bundle_root")
if root != "/Workspace/bundles/.bundle/canopy/canopy-hgb-sandbox-5dt024/sandbox/files":
    raise ValueError("Unexpected sandbox source root")
sys.path.insert(0, root)
from service.run_trip import main
result = main(["--trip-id", dbutils.widgets.get("trip_id"),
               "--user-id", dbutils.widgets.get("user_id"),
               "--processing-generation", dbutils.widgets.get("processing_generation")])
output = json.dumps(result, ensure_ascii=False, allow_nan=False)
if len(output.encode("utf-8")) > 4000000:
    raise ValueError("HGB result exceeds app output limit")
dbutils.notebook.exit(output)
