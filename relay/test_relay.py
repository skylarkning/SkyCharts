import unittest
from unittest.mock import patch

import msfs_chart_relay as relay


class RelayTests(unittest.TestCase):
    def setUp(self):
        relay.cache.expires = 0
        relay.cache.light = None
        relay.cache.dark = None
        relay.cache.metadata = None

    def test_flatten_charts(self):
        payload = {"charts": {"airport": {"AGC": [{"guid": "g", "name": "Airport Ground Chart AGC"}]}, "SID": []}}
        self.assertEqual([c["name"] for c in relay.flatten_charts(payload)], ["Airport Ground Chart AGC"])

    def test_flatten_does_not_return_non_chart_metadata(self):
        payload = {"metadata": {"name": "Airport Ground Chart AGC"}, "charts": []}
        self.assertEqual(list(relay.flatten_charts(payload)), [])

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_auth_is_explicit(self):
        with self.assertRaisesRegex(relay.RelayError, "MSFS_SESSION_COOKIE"):
            relay.planner_request("/api/v1/test")

    @patch("msfs_chart_relay.fetch_binary", side_effect=[b"light", b"dark"])
    @patch("msfs_chart_relay.planner_request")
    def test_fetch_agc_builds_signed_urls(self, request, fetch):
        request.side_effect = [
            {"charts": {"AGC": [{"guid": "chart-guid", "type": "AGC", "name": "Airport Ground Chart AGC", "aircraftTypes": []}]}},
            {"pages": [{"urls": {"light_png": "https://blob/light.png", "dark_png": "https://blob/dark.png"}}]},
            "sv=fake&sig=fake",
        ]
        metadata, light, dark = relay.fetch_agc()
        self.assertEqual(metadata["type"], "AGC")
        self.assertEqual((light, dark), (b"light", b"dark"))
        self.assertEqual(fetch.call_args_list[0].args[0], "https://blob/light.png?sv=fake&sig=fake")
        self.assertEqual(fetch.call_args_list[1].args[0], "https://blob/dark.png?sv=fake&sig=fake")

    @patch("msfs_chart_relay.fetch_binary", side_effect=[b"light", b"dark"])
    @patch("msfs_chart_relay.planner_request")
    def test_fetch_agc_accepts_live_lido_schema(self, request, fetch):
        request.side_effect = [
            {"charts": {"AGC": [
                {"guid": "standard", "type": "AGC", "name": "AGC", "aircraftTypes": []},
                {"guid": "widebody", "type": "AGC", "name": "AGC A346 ONLY", "aircraftTypes": ["A346"]},
            ]}},
            {"pages": [{"urls": {"light_png": "https://blob/light.png", "dark_png": "https://blob/dark.png"}}]},
            "sv=fake&sig=fake",
        ]
        metadata, light, dark = relay.fetch_agc()
        self.assertEqual(metadata["name"], "Airport Ground Chart AGC")
        self.assertEqual(request.call_args_list[1].args[0], "/api/v1/charts/pages/standard")


if __name__ == "__main__":
    unittest.main()
