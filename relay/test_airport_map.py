import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import skycharts_airport_map as airport_map


class AirportMapTests(unittest.TestCase):
    def test_normalizes_airport_geometry_and_counts(self):
        raw = {
            "elements": [
                {"type": "way", "id": 1, "tags": {"aeroway": "runway", "ref": "04/22"},
                 "geometry": [{"lat": 40.0, "lon": -73.1}, {"lat": 40.01, "lon": -73.0}]},
                {"type": "way", "id": 2, "tags": {"aeroway": "taxiway", "ref": "A"},
                 "geometry": [{"lat": 40.001, "lon": -73.09}, {"lat": 40.005, "lon": -73.03}]},
                {"type": "node", "id": 3, "lat": 40.003, "lon": -73.04,
                 "tags": {"aeroway": "parking_position", "ref": "12"}},
                {"type": "way", "id": 4, "tags": {"aeroway": "apron"},
                 "geometry": [{"lat": 40.002, "lon": -73.06}, {"lat": 40.004, "lon": -73.06},
                              {"lat": 40.004, "lon": -73.02}, {"lat": 40.002, "lon": -73.06}]},
                {"type": "way", "id": 5, "tags": {"building": "terminal", "name": "New Terminal 1"},
                 "geometry": [{"lat": 40.002, "lon": -73.05}, {"lat": 40.003, "lon": -73.05},
                              {"lat": 40.003, "lon": -73.04}, {"lat": 40.002, "lon": -73.05}]},
            ]
        }
        result = airport_map.normalize(raw, {"ident": "TEST", "name": "Test Airport", "latitude": 40.0, "longitude": -73.0})
        self.assertEqual(result["counts"]["runway"], 1)
        self.assertEqual(result["counts"]["taxiway"], 1)
        self.assertEqual(result["counts"]["parking_position"], 1)
        self.assertTrue(next(feature for feature in result["features"] if feature["kind"] == "apron")["closed"])
        self.assertEqual(next(feature for feature in result["features"] if feature["kind"] == "terminal")["label"], "T1")
        self.assertLess(result["bounds"]["minLon"], -73.1)
        self.assertGreater(result["bounds"]["maxLat"], 40.01)

    def test_rejects_empty_geometry(self):
        with self.assertRaises(airport_map.AirportMapError):
            airport_map.normalize({"elements": []}, {"ident": "TEST", "name": "Test", "latitude": 0, "longitude": 0})

    def test_query_requests_required_feature_types(self):
        query = airport_map.overpass_query(40.0, -73.0)
        for value in ("runway", "taxiway", "apron", "parking_position"):
            self.assertIn(value, query)

    def test_terminal_labels_require_an_available_designator(self):
        self.assertEqual(airport_map.terminal_label({"ref": "T2", "name": "Domestic Terminal"}), "T2")
        self.assertEqual(airport_map.terminal_label({"name": "Terminal 4"}), "T4")
        self.assertEqual(airport_map.terminal_label({"name": "白云国际机场T1航站楼"}), "T1")
        self.assertIsNone(airport_map.terminal_label({"name": "International Terminal"}))

    def test_parses_osm_xml_for_standard_api_fallback(self):
        payload = b"""<osm>
          <node id="1" lat="40.0" lon="-73.0"/>
          <node id="2" lat="40.1" lon="-72.9"><tag k="aeroway" v="parking_position"/><tag k="ref" v="A1"/></node>
          <way id="7"><nd ref="1"/><nd ref="2"/><tag k="aeroway" v="taxiway"/><tag k="ref" v="A"/></way>
        </osm>"""
        nodes, ways = {}, {}
        airport_map.parse_osm_xml(payload, nodes, ways)
        self.assertEqual(nodes["2"]["tags"]["ref"], "A1")
        self.assertEqual(ways["7"]["refs"], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
