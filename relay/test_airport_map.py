import io
import json
import pathlib
import sys
import tempfile
import threading
import time
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
        self.assertIn('way["building"="terminal"]', query)
        self.assertIn('relation["building"="terminal"]', query)
        self.assertIn("out body geom", query)

    def test_normalizes_split_terminal_multipolygon_relations(self):
        raw = {"elements": [{
            "type": "relation", "id": 91,
            "tags": {"type": "multipolygon", "building": "terminal", "name": "Terminal 3"},
            "members": [
                {"type": "way", "role": "outer", "geometry": [
                    {"lat": 40.0, "lon": -73.0}, {"lat": 40.0, "lon": -72.9},
                ]},
                {"type": "way", "role": "outer", "geometry": [
                    {"lat": 40.1, "lon": -72.9}, {"lat": 40.1, "lon": -73.0},
                ]},
                {"type": "way", "role": "outer", "geometry": [
                    {"lat": 40.0, "lon": -72.9}, {"lat": 40.1, "lon": -72.9},
                ]},
                {"type": "way", "role": "outer", "geometry": [
                    {"lat": 40.1, "lon": -73.0}, {"lat": 40.0, "lon": -73.0},
                ]},
                {"type": "way", "role": "inner", "geometry": [
                    {"lat": 40.02, "lon": -72.98}, {"lat": 40.02, "lon": -72.96},
                    {"lat": 40.04, "lon": -72.96}, {"lat": 40.02, "lon": -72.98},
                ]},
            ],
        }]}
        result = airport_map.normalize(raw, {
            "ident": "TEST", "name": "Test Airport", "latitude": 40.0, "longitude": -73.0,
        })
        terminal = result["features"][0]
        self.assertEqual(result["counts"]["terminal"], 1)
        self.assertEqual(terminal["label"], "Terminal 3")
        self.assertTrue(terminal["closed"])
        self.assertEqual(len(terminal["points"]), 5)

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
110 1 0.25 0 New Taxiway 10
111 28.8400 115.8900
111 28.8800 115.8900
113 28.8800 115.9200
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

    def test_extracts_and_parses_gateway_terminal_facades(self):
        dsf_text = """PROPERTY sim/overlay 1
POLYGON_DEF lib/airport/Modern_Airports/Terminal_kit/term_building_Ground_01.fac
POLYGON_DEF lib/airport/ground/pavement/concrete.pol
BEGIN_POLYGON 0 383 2
BEGIN_WINDING
POLYGON_POINT 115.9000 28.8500
POLYGON_POINT 115.9010 28.8500
POLYGON_POINT 115.9010 28.8510
POLYGON_POINT 115.9000 28.8510
END_WINDING
END_POLYGON
BEGIN_POLYGON 1 0 2
BEGIN_WINDING
POLYGON_POINT 115.9100 28.8600
POLYGON_POINT 115.9110 28.8600
POLYGON_POINT 115.9110 28.8610
END_WINDING
END_POLYGON
"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("ZSCN.dat", "1 143 0 0 ZSCN Test Airport\n")
            archive.writestr("ZSCN.txt", dsf_text)
        text, name = airport_map.extract_xplane_dsf_text(buffer.getvalue(), "ZSCN")
        self.assertEqual(name, "ZSCN.txt")
        raw = airport_map.parse_xplane_dsf_terminals(text)
        self.assertEqual(len(raw["elements"]), 1)
        self.assertEqual(raw["elements"][0]["tags"]["building"], "terminal")
        self.assertEqual(raw["elements"][0]["geometry"][0], raw["elements"][0]["geometry"][-1])

    def test_gateway_terminals_use_ground_footprints_and_gate_proximity(self):
        dsf_text = """PROPERTY sim/overlay 1
POLYGON_DEF lib/airport/Modern_Airports/Terminal_kit/term_building_Ground_01.fac
POLYGON_DEF lib/airport/Modern_Airports/Terminal_kit/term_building_Levels_01.fac
POLYGON_DEF lib/airport/Modern_Airports/Facades/modern2.fac
BEGIN_POLYGON 0 0 2
BEGIN_WINDING
POLYGON_POINT -73.0000 45.0000
POLYGON_POINT -72.9990 45.0000
POLYGON_POINT -72.9990 45.0010
POLYGON_POINT -73.0000 45.0010
END_WINDING
END_POLYGON
BEGIN_POLYGON 1 0 2
BEGIN_WINDING
POLYGON_POINT -73.0000 45.0000
POLYGON_POINT -72.9990 45.0000
POLYGON_POINT -72.9990 45.0010
POLYGON_POINT -73.0000 45.0010
END_WINDING
END_POLYGON
BEGIN_POLYGON 2 0 2
BEGIN_WINDING
POLYGON_POINT -72.9800 45.0200
POLYGON_POINT -72.9790 45.0200
POLYGON_POINT -72.9790 45.0210
POLYGON_POINT -72.9800 45.0210
END_WINDING
END_POLYGON
"""
        anchors = [{"lat": 45.0005, "lon": -72.9995}]
        raw = airport_map.parse_xplane_dsf_terminals(dsf_text, anchors=anchors)
        self.assertEqual(len(raw["elements"]), 1)
        self.assertEqual(raw["elements"][0]["tags"]["building"], "terminal")

    def test_gateway_generic_modern_facade_recovers_older_terminal(self):
        dsf_text = """PROPERTY sim/overlay 1
POLYGON_DEF lib/airport/Modern_Airports/Facades/modern2.fac
BEGIN_POLYGON 0 0 2
BEGIN_WINDING
POLYGON_POINT -73.0000 45.0000
POLYGON_POINT -72.9980 45.0000
POLYGON_POINT -72.9980 45.0020
POLYGON_POINT -73.0000 45.0020
END_WINDING
END_POLYGON
"""
        raw = airport_map.parse_xplane_dsf_terminals(
            dsf_text, anchors=[{"lat": 45.0010, "lon": -72.9990}])
        self.assertEqual(len(raw["elements"]), 1)

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

    def test_build_refreshes_an_osm_cache_from_before_terminal_relation_support(self):
        old_cache = {
            "schemaVersion": 1,
            "ident": "CYYZ",
            "source": "OpenStreetMap contributors",
            "features": [{
                "kind": "runway", "ref": "05/23",
                "points": [[-79.64, 43.67], [-79.60, 43.69]],
            }],
        }
        fresh_raw = {"elements": [{
            "type": "way", "id": 1, "tags": {"aeroway": "runway", "ref": "05/23"},
            "geometry": [{"lat": 43.67, "lon": -79.64}, {"lat": 43.69, "lon": -79.60}],
        }, {
            "type": "way", "id": 2, "tags": {"building": "terminal", "name": "Terminal 3"},
            "geometry": [
                {"lat": 43.68, "lon": -79.63}, {"lat": 43.68, "lon": -79.62},
                {"lat": 43.69, "lon": -79.62}, {"lat": 43.68, "lon": -79.63},
            ],
        }]}
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = pathlib.Path(temporary) / "CYYZ.json"
            cache_path.write_text(json.dumps(old_cache), encoding="utf-8")
            with mock.patch.object(airport_map, "airport_record", return_value={
                    "ident": "CYYZ", "name": "Toronto Pearson", "latitude": 43.68, "longitude": -79.63,
                    }), \
                    mock.patch.object(airport_map, "fetch_overpass", return_value=fresh_raw), \
                    mock.patch.object(airport_map, "xplane_gateway_raw",
                                      side_effect=airport_map.XPlaneGatewayNoDataError("none")) as gateway:
                result, cached = airport_map.build_airport_map("CYYZ", cache_dir=temporary)
        self.assertFalse(cached)
        self.assertEqual(result["osmRevision"], airport_map.OSM_SOURCE_REVISION)
        self.assertEqual(result["counts"]["terminal"], 1)
        gateway.assert_called_once()

    def test_overpass_failure_uses_one_combined_query(self):
        with mock.patch.object(airport_map, "request_overpass", side_effect=airport_map.OverpassUnavailableError("offline")) as request:
            with self.assertRaises(airport_map.OverpassUnavailableError):
                airport_map.fetch_overpass(40, -73)
        request.assert_called_once()

    def test_overpass_waits_briefly_for_an_in_flight_endpoint(self):
        endpoint = "https://overpass.example/api/interpreter"
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"elements":[]}'
        with airport_map._ENDPOINT_CONDITION:
            airport_map._ENDPOINT_RETRY_AFTER.pop(endpoint, None)
            airport_map._ENDPOINT_IN_FLIGHT.add(endpoint)

        def release_endpoint():
            with airport_map._ENDPOINT_CONDITION:
                airport_map._ENDPOINT_IN_FLIGHT.discard(endpoint)
                airport_map._ENDPOINT_CONDITION.notify_all()

        timer = threading.Timer(0.03, release_endpoint)
        timer.start()
        started = time.monotonic()
        try:
            with mock.patch.object(airport_map, "OVERPASS_BUSY_WAIT", 0.25), \
                    mock.patch.object(airport_map.urllib.request, "urlopen", return_value=response) as urlopen:
                result = airport_map.request_overpass("[out:json];out;", (endpoint,), timeout=0.1)
        finally:
            timer.join()
            with airport_map._ENDPOINT_CONDITION:
                airport_map._ENDPOINT_IN_FLIGHT.discard(endpoint)
                airport_map._ENDPOINT_RETRY_AFTER.pop(endpoint, None)
        self.assertEqual(result, {"elements": []})
        self.assertGreaterEqual(time.monotonic() - started, 0.02)
        urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
