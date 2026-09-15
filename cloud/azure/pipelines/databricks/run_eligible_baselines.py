"""Job entry point for Git Folder or the extracted, source-controlled bundle."""
import argparse
import importlib
import json
import os
from pathlib import Path

from baseline_eligibility import load_eligibility_policy


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("personal", "global"))
    parser.add_argument("--campaign-id")
    parser.add_argument("--evaluation-week")
    parser.add_argument("--identities-file")
    parser.add_argument("--confirmed-commute-only", action="store_true",
                        help="Only after verifying that the input Weekly Gold trip_count counts confirmed commutes")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args(argv)
    policy = load_eligibility_policy()
    baseline_policy_path = Path(__file__).resolve().with_name("baseline_policy.yaml")
    if not baseline_policy_path.is_file():
        raise FileNotFoundError(baseline_policy_path)
    if args.check_config:
        print(json.dumps({"eligibility_policy_version": policy["policy_version"],
                          "baseline_policy_path": str(baseline_policy_path)}))
        return
    if not args.phase or not args.campaign_id:
        parser.error("--phase and --campaign-id are required")
    if args.phase == "global" and not args.evaluation_week:
        parser.error("--evaluation-week is required for Global")
    if args.identities_file:
        os.environ["CANOPY_BASELINE_IDENTITIES_PATH"] = args.identities_file
    if args.confirmed_commute_only:
        os.environ["CANOPY_BASELINE_WEEKLY_COMMUTE_VERIFIED"] = "true"
    module = importlib.import_module(f"build_{args.phase}_baseline")
    # Unlike the old notebook default, this policy is deployed with the code.
    module.BASELINE_POLICY_PATH = str(baseline_policy_path)
    if args.phase == "personal":
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        # Spark 4 Classic / Spark Connect: distribute modules, not YAML, to UDF workers.
        # The driver reads YAML once and passes the policy dictionary into the UDF.
        spark.addArtifact(str(Path(module.__file__).resolve()),
                          str(Path(__file__).resolve().with_name("baseline_eligibility.py")), pyfile=True)
        module.run(args.campaign_id)
    else:
        module.run(args.campaign_id, args.evaluation_week)


if __name__ == "__main__":
    main()
