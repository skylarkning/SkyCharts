import plistlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_public_and_internal_versions_are_separate(self):
        with (ROOT / "SkyCharts.plist").open("rb") as handle:
            metadata = plistlib.load(handle)

        public_version = metadata.get("SkyChartsPublicVersion", "")
        internal_version = metadata.get("CFBundleShortVersionString", "")
        build_number = metadata.get("CFBundleVersion", "")

        self.assertTrue(public_version.startswith("V"))
        self.assertTrue(internal_version)
        self.assertNotEqual(public_version, internal_version)
        self.assertTrue(str(build_number).isdigit())

    def test_about_page_reads_public_version(self):
        source = (ROOT / "SkyCharts" / "AboutViewController.m").read_text()
        self.assertIn('@"SkyChartsPublicVersion"', source)
        self.assertIn('%@ (Build %@)', source)


if __name__ == "__main__":
    unittest.main()
