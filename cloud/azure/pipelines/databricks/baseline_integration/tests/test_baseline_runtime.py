from baseline_runtime import (
    DEFAULT_GLOBAL_HISTORY_PATH,
    DEFAULT_PERSONAL_HISTORY_PATH,
    DEFAULT_WEEKLY_USER_PATH,
    build_cosmos_spark_options,
    load_cosmos_identity,
    load_cosmos_targets,
    load_gold_paths,
)


def test_gold_paths_default_to_teammate_merged_adls_paths():
    paths = load_gold_paths(environ={})
    assert paths.weekly_user == DEFAULT_WEEKLY_USER_PATH
    assert paths.personal_history == DEFAULT_PERSONAL_HISTORY_PATH
    assert paths.global_history == DEFAULT_GLOBAL_HISTORY_PATH
    assert paths.eligibility is None


def test_eligibility_path_is_optional_until_teammate_contract_lands():
    paths = load_gold_paths(
        environ={"CANOPY_BASELINE_ELIGIBILITY_PATH": "abfss://curated/eligibility"}
    )
    assert paths.eligibility.endswith("eligibility")


def test_gold_paths_allow_runtime_override():
    paths = load_gold_paths(
        environ={
            "CANOPY_GOLD_WEEKLY_USER_PATH": "abfss://gold/weekly_user",
            "CANOPY_GOLD_PERSONAL_BASELINE_PATH": "abfss://gold/personal",
            "CANOPY_GOLD_GLOBAL_BASELINE_PATH": "abfss://gold/global",
        }
    )
    assert paths.weekly_user.endswith("weekly_user")
    assert paths.personal_history.endswith("personal")
    assert paths.global_history.endswith("global")


def test_cosmos_managed_identity_options_contain_no_secret_material():
    env = {
        "CANOPY_COSMOS_ENDPOINT": "https://example.documents.azure.com:443/",
        "CANOPY_COSMOS_DATABASE": "canopy",
        "CANOPY_AZURE_SUBSCRIPTION_ID": "sub",
        "CANOPY_AZURE_TENANT_ID": "tenant",
        "CANOPY_AZURE_RESOURCE_GROUP": "rg",
        "CANOPY_COSMOS_MI_CLIENT_ID": "mi-client",
        "CANOPY_COSMOS_PERSONAL_BASELINE_CONTAINER": "personal",
        "CANOPY_COSMOS_GLOBAL_BASELINE_CONTAINER": "global",
    }
    identity = load_cosmos_identity(environ=env)
    targets = load_cosmos_targets(environ=env)
    options = build_cosmos_spark_options(identity, container=targets.personal_container)

    assert options["spark.cosmos.auth.type"] == "ManagedIdentity"
    assert options["spark.cosmos.auth.aad.clientId"] == "mi-client"
    assert options["spark.cosmos.write.strategy"] == "ItemOverwrite"
    assert options["spark.cosmos.container"] == "personal"
    assert not any("key" in name.lower() for name in options)
    assert not any("secret" in name.lower() for name in options)
