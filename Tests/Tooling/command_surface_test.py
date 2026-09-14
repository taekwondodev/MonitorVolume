#!/usr/bin/env python3

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CommandSurfaceTests(unittest.TestCase):
    def make(self, *targets: str) -> str:
        result = subprocess.run(
            ["make", *targets],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def make_dry_run(self, *targets: str) -> str:
        result = subprocess.run(
            ["make", "-n", *targets],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def test_bare_make_selects_help(self) -> None:
        self.assertEqual(self.make_dry_run(), self.make_dry_run("help"))
        self.assertEqual(self.make(), self.make("help"))

    def test_expected_targets_are_available(self) -> None:
        expected_commands = {
            "test": "swift test",
            "check": "scripts/check.sh",
            "build": "scripts/build-app.sh",
            "verify": "scripts/verify-installed-app.sh",
            "profile": "scripts/profile-app.sh",
            "clean": "swift package clean",
        }
        for target, expected_command in expected_commands.items():
            with self.subTest(target=target):
                self.assertIn(expected_command, self.make_dry_run(target))

    def test_clean_is_limited_to_swiftpm_artifacts(self) -> None:
        command = self.make_dry_run("clean")
        self.assertIn("swift package clean", command)
        self.assertNotIn("Applications", command)
        self.assertNotIn(".app", command)


if __name__ == "__main__":
    unittest.main()
