import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import skycharts_downloader as downloader


class BundledAirportMapTests(unittest.TestCase):
    def test_bundles_map_and_records_manifest_relative_path(self):
        airports = [{"ident": "KJFK", "categories": [{"name": "AIRPORT", "charts": []}]}]
        result = {"ident": "KJFK", "features": [{"kind": "runway", "points": [[0, 0], [1, 1]]}]}
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(downloader.skycharts_airport_map, "build_airport_map", return_value=(result, True)):
                count = downloader.bundle_airport_maps(airports, pathlib.Path(temporary), workers=2)
            self.assertEqual(count, 1)
            self.assertEqual(airports[0]["map"], "maps/KJFK.json")
            self.assertEqual((pathlib.Path(temporary) / "maps" / "KJFK.json").read_text(), '{"ident":"KJFK","features":[{"kind":"runway","points":[[0,0],[1,1]]}]}')


if __name__ == "__main__":
    unittest.main()
