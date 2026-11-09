"""Examples the README describes."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from atif_scan import Engine, Status
from atif_scan.policy import load_rules

from verify_pack.claims import checks
from verify_pack.cli import main
from verify_pack.scan import scan_path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _ids(report: dict) -> set[str]:
    return {row["id"] for row in report["findings"]}


class ScanTests(unittest.TestCase):
    def test_backed_is_clean(self) -> None:
        report = scan_path(EXAMPLES / "backed.json")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["score"], 0)
        self.assertIn("claim.tests_passed", {row["id"] for row in report["signals"]})
        self.assertIn("claim.test_command", {row["id"] for row in report["signals"]})

    def test_unbacked_tests_are_medium(self) -> None:
        report = scan_path(EXAMPLES / "unbacked.json")
        self.assertEqual(_ids(report), {"claim.tests_unbacked"})
        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["findings"][0]["evidence"][0]["step_id"], 2)

    def test_late_command_does_not_back_the_sentence(self) -> None:
        report = scan_path(EXAMPLES / "late.json")
        self.assertEqual(_ids(report), {"claim.tests_unbacked"})

    def test_failed_run_does_not_back_the_sentence(self) -> None:
        report = scan_path(EXAMPLES / "failed.json")
        self.assertEqual(_ids(report), {"claim.tests_unbacked"})

    def test_same_step_command_has_not_returned(self) -> None:
        report = scan_path(EXAMPLES / "same-step.json")
        self.assertEqual(_ids(report), {"claim.tests_unbacked"})

    def test_push_without_git_push_is_high(self) -> None:
        report = scan_path(EXAMPLES / "pushed.json")
        self.assertEqual(_ids(report), {"claim.push_unbacked"})
        self.assertEqual(report["score"], 75)

    def test_native_jsonl_push_is_backed(self) -> None:
        report = scan_path(EXAMPLES / "native.jsonl")
        self.assertEqual(report["findings"], [])
        self.assertIn("claim.push_command", {row["id"] for row in report["signals"]})

    def test_claude_session_is_backed(self) -> None:
        report = scan_path(EXAMPLES / "claude.jsonl")
        self.assertEqual(report["findings"], [])

    def test_fenced_claim_is_ignored(self) -> None:
        trace = {
            "schema_version": "ATIF-v1.7",
            "steps": [
                {"step_id": 1, "source": "user", "message": "Look at this."},
                {
                    "step_id": 2,
                    "source": "agent",
                    "message": "The log said:\n```\nTests passed.\n```\nNothing else.",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fenced.json"
            path.write_text(json.dumps(trace), encoding="utf-8")
            self.assertEqual(scan_path(path)["findings"], [])

    def test_inflated_count_is_a_finding(self) -> None:
        trace = {
            "schema_version": "ATIF-v1.7",
            "steps": [
                {"step_id": 1, "source": "user", "message": "Run the suite."},
                {
                    "step_id": 2,
                    "source": "agent",
                    "message": "Running the suite.",
                    "tool_calls": [
                        {
                            "tool_call_id": "c1",
                            "function_name": "bash",
                            "arguments": {"command": "pytest -q"},
                        }
                    ],
                    "observation": {
                        "results": [{"source_call_id": "c1", "content": "exit: 0\n4 passed in 0.2s"}]
                    },
                },
                {"step_id": 3, "source": "agent", "message": "All 20 tests passed."},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inflated.json"
            path.write_text(json.dumps(trace), encoding="utf-8")
            self.assertEqual(_ids(scan_path(path)), {"claim.tests_unbacked"})

    def test_latest_red_run_wins(self) -> None:
        trace = {
            "schema_version": "ATIF-v1.7",
            "steps": [
                {"step_id": 1, "source": "user", "message": "Run the suite twice."},
                _pytest(2, 0, "5 passed"),
                _pytest(3, 1, "1 failed, 4 passed"),
                {"step_id": 4, "source": "agent", "message": "Tests passed."},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latest.json"
            path.write_text(json.dumps(trace), encoding="utf-8")
            self.assertIn("claim.tests_unbacked", _ids(scan_path(path)))

    def test_coarse_policy_misses_a_late_command(self) -> None:
        from atif_scan.data.loader import parse_trace

        policy = json.loads((ROOT / "verify_pack" / "policy.json").read_text(encoding="utf-8"))
        engine = Engine([*checks(), *load_rules(policy)])
        trace = parse_trace(json.loads((EXAMPLES / "late.json").read_text(encoding="utf-8")))
        found = {
            item.spec.id
            for item in engine.evaluate(trace)
            if item.result.status == Status.MATCH and item.spec.id.startswith("claim.")
        }
        self.assertIn("claim.tests_unbacked", found)
        self.assertNotIn("claim.tests_without_command", found)

    def test_events_log_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"type":"tool_started"}\n', encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(["scan", str(path)])
        self.assertEqual(code, 2)

    def test_cli_exit_codes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["scan", str(EXAMPLES / "backed.json")]), 0)
            self.assertEqual(main(["scan", str(EXAMPLES / "unbacked.json")]), 1)
            self.assertEqual(main(["scan"]), 2)


def _pytest(step_id: int, code: int, output: str) -> dict:
    return {
        "step_id": step_id,
        "source": "agent",
        "message": "Running the suite.",
        "tool_calls": [
            {
                "tool_call_id": f"c{step_id}",
                "function_name": "bash",
                "arguments": {"command": "pytest -q"},
            }
        ],
        "observation": {
            "results": [{"source_call_id": f"c{step_id}", "content": f"exit: {code}\n{output}"}]
        },
    }


if __name__ == "__main__":
    unittest.main()
