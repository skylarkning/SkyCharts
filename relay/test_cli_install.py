import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import skycharts_cli


class DebInstallerTests(unittest.TestCase):
    def test_installer_uses_legacy_ssh_flags_dpkg_mobile_uicache_and_respring(self):
        with tempfile.TemporaryDirectory() as directory:
            deb = pathlib.Path(directory) / "SkyCharts-0.15.7-ios6-armv7.deb"
            deb.write_bytes(b"deb")
            commands = []

            def record(command, cwd=None, env=None):
                commands.append(command)
                return 0

            with mock.patch.object(skycharts_cli.shutil, "which", return_value="/usr/bin/tool"), \
                    mock.patch.object(skycharts_cli.subprocess, "call", side_effect=record):
                self.assertEqual(skycharts_cli.install_deb(deb, "192.0.2.6", "secret"), 0)

            self.assertEqual(len(commands), 3)
            transfer = " ".join(commands[0])
            install = " ".join(commands[1])
            respring = " ".join(commands[2])
            self.assertIn("scp -O", transfer)
            self.assertIn("HostKeyAlgorithms=+ssh-rsa", transfer)
            self.assertIn("KexAlgorithms=+diffie-hellman-group14-sha1", transfer)
            self.assertIn("dpkg -i /tmp/SkyCharts.deb", install)
            self.assertIn("su mobile -c /usr/bin/uicache", install)
            self.assertIn("/var/mobile/Applications/*/SkyCharts.app", install)
            self.assertIn("killall SpringBoard", respring)
            self.assertNotIn("secret", transfer + install + respring)

    def test_latest_deb_uses_most_recent_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            older = root / "SkyCharts-0.15.6-ios6-armv7.deb"
            newer = root / "SkyCharts-0.15.7-ios6-armv7.deb"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")
            older.touch()
            newer.touch()
            older_mtime = older.stat().st_mtime - 10
            import os
            os.utime(str(older), (older_mtime, older_mtime))
            self.assertEqual(skycharts_cli.latest_deb(root), newer)


class EnvironmentAuditTests(unittest.TestCase):
    def test_audit_maps_missing_commands_to_homebrew_formulas(self):
        def which(command):
            return "/usr/bin/%s" % command if command in ("python3", "git") else None

        with mock.patch.object(skycharts_cli, "playwright_status", return_value=False):
            status = skycharts_cli.environment_status(which=which)
        by_command = {item["command"]: item for item in status}
        self.assertTrue(by_command["python3"]["available"])
        self.assertFalse(by_command["sshpass"]["available"])
        self.assertEqual(by_command["sshpass"]["formula"], "sshpass")
        self.assertFalse(by_command["playwright"]["available"])


if __name__ == "__main__":
    unittest.main()
