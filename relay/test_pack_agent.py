import pathlib
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import skycharts_pack_agent as agent


class PackArchiveTests(unittest.TestCase):
    def test_build_archive_is_single_stream_ustar_with_manifest_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            pack = root / "job"
            (pack / "charts" / "one").mkdir(parents=True)
            (pack / "maps").mkdir(parents=True)
            (pack / "pack.json").write_text('{"packId":"test"}', encoding="utf-8")
            (pack / "charts" / "one" / "0-light.png").write_bytes(b"PNG")
            (pack / "maps" / "KJFK.json").write_text('{"ident":"KJFK"}', encoding="utf-8")
            archive_path, count = agent.build_archive("job", pack)
            self.assertEqual(count, 3)
            with tarfile.open(archive_path, "r:") as archive:
                self.assertEqual(archive.getnames(), ["pack.json", "charts/one/0-light.png", "maps/KJFK.json"])
                self.assertEqual(archive.extractfile("charts/one/0-light.png").read(), b"PNG")

    def test_public_job_does_not_expose_mac_archive_path(self):
        result = agent.public_job({"id": "x", "archive": "/packs/x/pack.tar", "archivePath": pathlib.Path("/private/archive")})
        self.assertNotIn("archivePath", result)
        self.assertEqual(result["archive"], "/packs/x/pack.tar")


if __name__ == "__main__":
    unittest.main()
