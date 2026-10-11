#!/usr/bin/env python3
"""unittest for task_router non-interactive classify. No network."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "task_router.py"


def run_router(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "JEV_DISABLE": "1"},
        check=False,
    )


class TaskRouterCliTest(unittest.TestCase):
    def test_task_flag_returns_json_difficulty_and_alias(self):
        proc = run_router("--task", "rename this variable to snake_case", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["level"], "easy")
        self.assertEqual(data["alias"], "deepseek")
        self.assertEqual(data["alternates"], ["qwen"])
        self.assertIn("heuristic", data["source"])
        self.assertNotIn("OPENROUTER_API_KEY", proc.stdout + proc.stderr)

    def test_hard_keyword_maps_to_opencode_zen(self):
        proc = run_router("--task", "refactor the distributed architecture from scratch", "--json")
        data = json.loads(proc.stdout)
        self.assertEqual(data["level"], "hard")
        self.assertEqual(data["alias"], "opencode-zen:claude-opus-5-5")
        self.assertEqual(data["alternates"], [])
        self.assertEqual(data["command"], "/model opencode-zen:claude-opus-5-5")

    def test_empty_task_exits_nonzero(self):
        proc = run_router("--task", "   ", "--json")
        self.assertNotEqual(proc.returncode, 0)

    def test_stdin_when_task_is_dash(self):
        proc = run_router("--task", "-", "--json", stdin="hello\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["level"], "easy")

    def test_medium_keyword(self):
        proc = run_router("--task", "debug this scraper bug", "--json")
        data = json.loads(proc.stdout)
        self.assertEqual(data["level"], "medium")
        self.assertEqual(data["alias"], "grok")
        self.assertEqual(data["command"], "/model grok")


if __name__ == "__main__":
    unittest.main()
