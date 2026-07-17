import io
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

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
        self.assertEqual(next(feature for feature in result["features"] if feature["kind"] == "terminal")["label"], "Terminal 1")
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
        self.assertEqual(airport_map.terminal_label({"ref": "T2", "name": "Domestic Terminal"}), "Terminal 2")
        self.assertEqual(airport_map.terminal_label({"name": "Terminal 4"}), "Terminal 4")
        self.assertEqual(airport_map.terminal_label({"name": "白云国际机场T1航站楼"}), "Terminal 1")
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

    def test_parses_xplane_gateway_airport_data(self):
        payload = """I
1200 Version
1 143 0 0 ZSCN Nanchang Changbei
100 45 1 0 0.25 1 1 0 03 28.8500 115.8950 0 0 1 0 0 0 21 28.8790 115.9090
110 1 0.25 0 Main Apron
111 28.8500 115.9000
111 28.8510 115.9000
113 28.8510 115.9010
1201 28.8500 115.9000 both 1 start
1201 28.8510 115.9010 both 2 end
1202 1 2 twoway taxiway_E J1
1300 28.8505 115.9005 90 gate jets Gate B12
99
"""
        raw = airport_map.parse_xplane_apt(payload, "ZSCN")
        result = airport_map.normalize(raw, {
            "ident": "ZSCN", "name": "Nanchang", "latitude": 28.86, "longitude": 115.90,
        }, source="X-Plane Scenery Gateway")
        self.assertEqual(result["counts"]["runway"], 1)
        self.assertEqual(result["counts"]["taxiway"], 1)
        self.assertEqual(result["counts"]["apron"], 1)
        self.assertEqual(result["counts"]["gate"], 1)
        self.assertEqual(next(feature for feature in result["features"] if feature["kind"] == "taxiway")["ref"], "J1")
        self.assertEqual(next(feature for feature in result["features"] if feature["kind"] == "gate")["ref"], "B12")

    def test_extracts_airport_dat_from_gateway_zip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", "ignore")
            archive.writestr("ZSCN.dat", "1 143 0 0 ZSCN Test Airport\n")
        text, name = airport_map.extract_xplane_apt(buffer.getvalue(), "ZSCN")
        self.assertIn("ZSCN Test Airport", text)
        self.assertEqual(name, "ZSCN.dat")

    def test_build_uses_gateway_when_overpass_is_unavailable(self):
        gateway = {
            "elements": [{
                "type": "way", "id": "gateway-runway", "tags": {"aeroway": "runway", "ref": "03/21"},
                "geometry": [{"lat": 28.85, "lon": 115.89}, {"lat": 28.88, "lon": 115.91}],
            }]
        }
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(airport_map, "airport_record", return_value={
                    "ident": "ZSCN", "name": "Nanchang", "latitude": 28.86, "longitude": 115.90,
                }), \
                mock.patch.object(airport_map, "fetch_overpass", side_effect=airport_map.OverpassUnavailableError("offline")), \
                mock.patch.object(airport_map, "xplane_gateway_raw", return_value=gateway):
            result, cached = airport_map.build_airport_map("ZSCN", cache_dir=temporary)
        self.assertFalse(cached)
        self.assertEqual(result["source"], "X-Plane Scenery Gateway")
        self.assertEqual(result["counts"]["runway"], 1)

    def test_overpass_failure_uses_one_combined_query(self):
        with mock.patch.object(airport_map, "request_overpass", side_effect=airport_map.OverpassUnavailableError("offline")) as request:
            with self.assertRaises(airport_map.OverpassUnavailableError):
                airport_map.fetch_overpass(40, -73)
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
