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

    def test_deb_system_app_keeps_shared_storage_access(self):
        with (ROOT / "SkyCharts.entitlements").open("rb") as handle:
            entitlements = plistlib.load(handle)

        self.assertIs(entitlements.get("platform-application"), True)
        self.assertIs(
            entitlements.get("com.apple.private.security.no-container"), True
        )
        self.assertIs(
            entitlements.get("com.apple.private.security.container-required"), False
        )

    def test_runtime_storage_prefers_shared_jailbreak_library(self):
        source = (ROOT / "SkyCharts" / "StoragePaths.m").read_text()
        chart = (ROOT / "SkyCharts" / "ChartViewController.m").read_text()
        content = (ROOT / "SkyCharts" / "ContentManagerViewController.m").read_text()

        self.assertIn('/var/mobile/Library/SkyCharts', source)
        self.assertIn('NSDocumentDirectory', source)
        self.assertIn('SkyChartsDirectoryIsWritable', source)
        self.assertIn('SkyChartsChartPackRoot()', chart)
        self.assertIn('SkyChartsChartPackRoot()', content)

    def test_distribution_is_deb_only(self):
        makefile = (ROOT / "Makefile").read_text()
        self.assertIn("include $(THEOS_MAKE_PATH)/application.mk", makefile)
        self.assertIn("SkyCharts_INSTALL_PATH = /Applications", makefile)


if __name__ == "__main__":
    unittest.main()
