import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import skycharts_cli


class AirportMapCacheManagerTests(unittest.TestCase):
    def test_lists_and_deletes_selected_airport_map_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for ident, name in (("KJFK", "John F Kennedy International"), ("CYYZ", "Toronto Pearson")):
                payload = {
                    "ident": ident,
                    "name": name,
                    "generatedAt": "2026-07-16T12:00:00+00:00",
                    "counts": {"parking_position": 12},
                    "features": [{"kind": "runway"}, {"kind": "taxiway"}],
                }
                (root / (ident + ".json")).write_text(json.dumps(payload), encoding="utf-8")

            entries = skycharts_cli.airport_map_cache_entries(root)
            self.assertEqual([entry["ident"] for entry in entries], ["CYYZ", "KJFK"])
            self.assertEqual(entries[0]["stands"], 12)

            removed = skycharts_cli.delete_airport_map_cache(["KJFK"], root)
            self.assertEqual(removed, ["KJFK"])
            self.assertFalse((root / "KJFK.json").exists())
            self.assertTrue((root / "CYYZ.json").exists())

    def test_unreadable_cache_entry_remains_manageable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "TEST.json"
            path.write_text("not json", encoding="utf-8")
            entries = skycharts_cli.airport_map_cache_entries(path.parent)
            self.assertEqual(entries[0]["ident"], "TEST")
            self.assertEqual(skycharts_cli.delete_airport_map_cache(["TEST"], path.parent), ["TEST"])


if __name__ == "__main__":
    unittest.main()
