import unittest

from gps_ingestion.event_hubs_auth import connection_string, jaas_config, normalized_policy_key


class EventHubsAuthTest(unittest.TestCase):
    def test_normalizes_terminal_whitespace(self) -> None:
        self.assertEqual(normalized_policy_key("abc123\r\n"), "abc123")

    def test_empty_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "policy key is empty"):
            normalized_policy_key(" \r\n\t")

    def test_blank_namespace_and_policy_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "namespace is empty"):
            connection_string(" ", "listen", "key")
        with self.assertRaisesRegex(ValueError, "policy name is empty"):
            connection_string("namespace", " ", "key")

    def test_jaas_escapes_quotes_and_backslashes_without_line_terminators(self) -> None:
        connection = connection_string("example", "listen", 'key\\"value\r')
        jaas = jaas_config(connection)
        self.assertNotIn("\r", jaas)
        self.assertNotIn("\n", jaas)
        self.assertIn(r'key\\\"value', jaas)
        self.assertNotIn('password="Endpoint=sb://example.servicebus.windows.net/;SharedAccessKeyName=listen;SharedAccessKey=key\\"value";', jaas)


if __name__ == "__main__":
    unittest.main()
