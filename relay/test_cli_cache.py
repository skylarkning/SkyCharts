import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import skycharts_cli
import skycharts_downloader


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

    def test_negative_cache_markers_are_hidden_and_deleted_with_airport(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            marker = root / "ZSCN.unavailable.json"
            marker.write_text(json.dumps({"reason": "temporary", "retryAfter": 9999999999}), encoding="utf-8")
            self.assertEqual(skycharts_cli.airport_map_cache_entries(root), [])
            self.assertEqual(skycharts_cli.delete_airport_map_cache(["ZSCN"], root), [])
            self.assertFalse(marker.exists())


class ChartAssetCacheManagerTests(unittest.TestCase):
    def write_chart(self, root, guid):
        asset = root / "charts" / guid / "0-light.png"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes((guid + "-image").encode("ascii"))
        metadata = root / guid / "metadata.json"
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(json.dumps({"guid": guid, "pages": [{"light": "charts/%s/0-light.png" % guid}]}), encoding="utf-8")

    def test_groups_legacy_charts_by_manifest_and_deletes_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            cache = base / "cache"
            manifests = base / "jobs"
            for guid in ("chart-a", "chart-shared", "chart-unknown"):
                self.write_chart(cache, guid)
            pack = {
                "airports": [
                    {"ident": "KAAA", "name": "Alpha Airport", "categories": [{"name": "APP", "charts": [
                        {"guid": "chart-a", "name": "Alpha Approach", "type": "IAC"},
                        {"guid": "chart-shared", "name": "Shared Chart", "type": "AGC"},
                    ]}]},
                    {"ident": "KBBB", "name": "Bravo Airport", "categories": [{"name": "TAXI", "charts": [
                        {"guid": "chart-shared", "name": "Shared Chart", "type": "AGC"},
                    ]}]},
                ]
            }
            manifests.mkdir(parents=True)
            (manifests / "pack.json").write_text(json.dumps(pack), encoding="utf-8")

            entries = skycharts_cli.chart_cache_entries(cache, [manifests])
            airports = skycharts_cli.chart_cache_airports(entries)
            self.assertEqual(set(airports), {"KAAA", "KBBB"})
            self.assertEqual(len(airports["KAAA"]["guids"]), 2)
            self.assertEqual(len([entry for entry in entries if not entry["airports"]]), 1)

            removed, removed_size = skycharts_cli.delete_chart_cache_airports(["KAAA"], cache, [manifests])
            self.assertEqual(set(removed), {"chart-a"})
            self.assertGreater(removed_size, 0)
            self.assertFalse((cache / "chart-a").exists())
            self.assertTrue((cache / "chart-shared").exists())
            self.assertTrue((cache / "chart-unknown").exists())
            index = json.loads((cache / "index.json").read_text(encoding="utf-8"))
            self.assertEqual({item["guid"] for item in index["charts"]}, {"chart-shared", "chart-unknown"})

    def test_new_download_metadata_records_airport_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            chart = {"guid": "guid-1", "name": "ILS 05", "type": "IAC"}
            pages = [{"light": "charts/guid-1/0-light.png"}]
            airport = {"ident": "CYYZ", "name": "Toronto Pearson"}
            skycharts_downloader.write_chart_cache_metadata(chart, pages, root, airport, "APPROACH")
            metadata = json.loads((root / "guid-1" / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["name"], "ILS 05")
            self.assertEqual(metadata["airports"][0]["ident"], "CYYZ")
            self.assertEqual(metadata["airports"][0]["category"], "APPROACH")

    def test_combined_package_cache_groups_and_deletes_chart_and_map_data(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            chart_cache = base / "charts"
            map_cache = base / "maps"
            self.write_chart(chart_cache, "chart-alpha")
            metadata_path = chart_cache / "chart-alpha" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["airports"] = [{"ident": "KAAA", "name": "Alpha Airport"}]
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            map_cache.mkdir()
            (map_cache / "KAAA.json").write_text(json.dumps({
                "ident": "KAAA", "name": "Alpha Airport", "generatedAt": "2026-07-16T12:00:00Z",
                "counts": {"parking_position": 2}, "features": [{"kind": "runway"}],
            }), encoding="utf-8")

            chart_entries = skycharts_cli.chart_cache_entries(chart_cache, manifest_roots=())
            map_entries = skycharts_cli.airport_map_cache_entries(map_cache)
            packages = skycharts_cli.airport_package_cache_entries(chart_entries, map_entries)
            self.assertEqual(set(packages), {"KAAA"})
            self.assertEqual(packages["KAAA"]["charts"], 1)
            self.assertTrue(packages["KAAA"]["has_map"])

            result = skycharts_cli.delete_airport_package_cache(
                ["KAAA"], chart_cache, map_cache, manifest_roots=())
            self.assertEqual(result["charts"], ["chart-alpha"])
            self.assertEqual(result["maps"], ["KAAA"])
            self.assertFalse((chart_cache / "chart-alpha").exists())
            self.assertFalse((map_cache / "KAAA.json").exists())


if __name__ == "__main__":
    unittest.main()
