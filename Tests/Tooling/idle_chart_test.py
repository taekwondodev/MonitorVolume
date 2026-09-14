#!/usr/bin/env python3

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import app_tool  # noqa: E402


class IdleChartTests(unittest.TestCase):
    def test_fixture_baseline_renders_paired_cpu_and_fails_when_missing(self) -> None:
        samples = [
            {"cpu_s": 0.0, "wall_s": 10.0},
            {"cpu_s": 0.01, "wall_s": 11.0},
            {"cpu_s": 0.03, "wall_s": 12.0},
        ]
        self.assertEqual(app_tool.idle_cpu_percent(samples), 1.5)
        fixture = {
            "bundle_size_bytes": 5 * 1024 * 1024,
            "idle_cpu_percent": 1.25,
            "physical_footprint_bytes": 16 * 1024 * 1024,
            "provenance": {"machine_model": "fixture"},
            "schema": 1,
            "state": "idle",
        }
        chart = app_tool.render_idle_chart(fixture)
        self.assertIn("1.250%", chart)
        self.assertIn("16.00 MiB", chart)
        self.assertIn("5.00 MiB", chart)
        with tempfile.TemporaryDirectory() as scratch:
            missing = Path(scratch) / "idle-baseline.json"
            chart_path = Path(scratch) / "idle.svg"
            with self.assertRaises(RuntimeError):
                app_tool.load_idle_baseline(missing)
            with self.assertRaises(RuntimeError):
                app_tool.write_idle_chart(missing, chart_path)
            self.assertFalse(chart_path.exists())
            baseline = Path(scratch) / "idle-baseline.json"
            baseline.write_text(json.dumps(fixture))
            app_tool.write_idle_chart(baseline, chart_path)
            rendered = chart_path.read_text()
            self.assertIn("1.250%", rendered)
            self.assertIn("16.00 MiB", rendered)
            self.assertIn("5.00 MiB", rendered)


if __name__ == "__main__":
    unittest.main()
