import unittest

from cloud.azure.pipelines.gps_streaming.event_hubs_auth import (
    connection_string,
    jaas_config,
    normalized_policy_key,
)


class EventHubsAuthTest(unittest.TestCase):
    def test_normalizes_trailing_carriage_return(self) -> None:
        self.assertEqual(normalized_policy_key("abc123\r"), "abc123")

    def test_jaas_contains_no_line_terminators_after_normalization(self) -> None:
        connection = connection_string(
            "example",
            "listen-only",
            "dummy-key\r",
        )
        jaas = jaas_config(connection)

        self.assertNotIn("\r", jaas)
        self.assertNotIn("\n", jaas)
        self.assertIn("SharedAccessKey=dummy-key", jaas)

    def test_empty_key_after_normalization_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Event Hubs SAS policy key is empty after normalization",
        ):
            normalized_policy_key(" \r\n\t")


if __name__ == "__main__":
    unittest.main()
