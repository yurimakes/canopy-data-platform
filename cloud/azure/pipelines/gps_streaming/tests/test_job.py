import unittest

from cloud.azure.pipelines.gps_streaming.job import parse_args


class JobArgumentsTest(unittest.TestCase):
    def test_all_workspace_owned_values_are_explicit(self) -> None:
        args = parse_args(
            [
                "--catalog", "catalog_dev",
                "--bronze-schema", "bronze_dev",
                "--silver-schema", "silver_dev",
                "--gold-schema", "gold_dev",
                "--bronze-events-table", "events",
                "--observations-table", "observations",
                "--quarantine-table", "quarantine",
                "--features-table", "features",
                "--segments-table", "segments",
                "--predictions-table", "predictions",
                "--checkpoint-root", "/Volumes/catalog_dev/bronze_dev/checkpoints",
                "--event-hubs-bootstrap-servers", "example.servicebus.windows.net:9093",
                "--event-hubs-topic", "gps",
                "--event-hubs-consumer-group", "canopy",
                "--event-hubs-secret-scope", "scope",
                "--event-hubs-secret-key", "key",
                "--model-uri", "models:/catalog_dev.gold_dev.model@champion",
            ]
        )
        self.assertEqual(args.catalog, "catalog_dev")
        self.assertEqual(args.features_table, "features")
        self.assertEqual(args.trigger_interval, "10 seconds")


if __name__ == "__main__":
    unittest.main()
