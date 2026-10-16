#!/usr/bin/env python3
"""Focused self-tests for the AI asset neutrality check."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("check-agent-neutrality.py")
SPEC = importlib.util.spec_from_file_location("check_agent_neutrality", SCRIPT_PATH)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)


class AgentNeutralityGuardTest(unittest.TestCase):
    def test_scans_ai_assets_not_unrelated_product_code(self) -> None:
        self.assertTrue(GUARD.should_scan(Path("skills/example/SKILL.md")))
        self.assertTrue(GUARD.should_scan(Path("evals/example/evals.json")))
        self.assertFalse(GUARD.should_scan(Path("evals/example/fixtures/input.md")))
        self.assertTrue(GUARD.should_scan(Path("skills/example/assets/template.md")))
        self.assertFalse(GUARD.should_scan(Path("skills/example/assets/icon.png")))
        self.assertTrue(GUARD.should_scan(Path("README.md")))
        self.assertTrue(GUARD.should_scan(Path("rules/example.md")))
        self.assertFalse(GUARD.should_scan(Path("packages/product/src/page.tsx")))
        self.assertFalse(GUARD.should_scan(Path("skills/example/tests/test.py")))

    def test_host_adapter_exemption_stays_narrow(self) -> None:
        for path in GUARD.HOST_ADAPTER_FILES:
            self.assertFalse(GUARD.should_scan(Path(path)))
            self.assertTrue(
                (GUARD.REPO_ROOT / path).exists(),
                f"{path} is exempt but missing; drop the exemption instead of keeping it stale",
            )
        self.assertTrue(GUARD.should_scan(Path("skills/rules-sync/SKILL.md")))

    def test_rejects_host_specific_workflow(self) -> None:
        patterns = dict(GUARD.RULES)
        self.assertIsNotNone(patterns["vendor-runtime-path"].search("write to ~/.claude/state"))
        self.assertIsNotNone(patterns["vendor-tool-invocation"].search("Agent(subagent_type=x)"))
        self.assertIsNotNone(patterns["vendor-workflow"].search("Install this for Gemini CLI"))

    def test_source_format_allowance_does_not_exempt_execution_host(self) -> None:
        allowed = '"Cursor CLI store.db is absent; no transcript content was fabricated.",'
        paths = list(GUARD.SOURCE_FORMAT_LINES)
        with tempfile.TemporaryDirectory() as temporary_directory:
            original_root = GUARD.REPO_ROOT
            try:
                GUARD.REPO_ROOT = Path(temporary_directory)
                for name in paths:
                    path = Path(name)
                    self.assertTrue(GUARD.should_scan(path))
                    target = GUARD.REPO_ROOT / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(allowed + "\n", encoding="utf-8")
                    self.assertEqual(GUARD.scan_file(path), [])
                    for bad in ("Requires Cursor CLI", "Run Claude CLI", "Agent(subagent_type=x)"):
                        target.write_text(allowed + "\n" + bad, encoding="utf-8")
                        self.assertTrue(GUARD.scan_file(path), bad)
                other = Path("skills/example/SKILL.md")
                (GUARD.REPO_ROOT / other).parent.mkdir(parents=True)
                (GUARD.REPO_ROOT / other).write_text(allowed, encoding="utf-8")
                self.assertTrue(GUARD.scan_file(other))
            finally:
                GUARD.REPO_ROOT = original_root

    def test_rejects_fixed_commit_trailer(self) -> None:
        self.assertIsNotNone(
            GUARD.FIXED_TRAILER.search("Co-authored-by: Example Agent <agent@example.com>")
        )
        self.assertIsNone(
            GUARD.FIXED_TRAILER.search("Add a trailer only when repository rules require one.")
        )

    def test_read_errors_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            original_root = GUARD.REPO_ROOT
            try:
                GUARD.REPO_ROOT = Path(temporary_directory)
                findings = GUARD.scan_file(Path("skills/missing/SKILL.md"))
            finally:
                GUARD.REPO_ROOT = original_root
        self.assertTrue(any("read-error" in finding for finding in findings))

    def test_non_utf8_scanned_files_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "asset.bin"
            target.write_bytes(b"\xff\xfe")
            original_root = GUARD.REPO_ROOT
            try:
                GUARD.REPO_ROOT = root
                findings = GUARD.scan_file(Path("asset.bin"))
            finally:
                GUARD.REPO_ROOT = original_root
        self.assertTrue(any("read-error" in finding for finding in findings))

    def test_symlink_target_is_scanned_without_following(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            link = root / "host-link"
            link.symlink_to("../../.trae/skills/example")
            original_root = GUARD.REPO_ROOT
            try:
                GUARD.REPO_ROOT = root
                findings = GUARD.scan_file(Path("host-link"))
            finally:
                GUARD.REPO_ROOT = original_root
        self.assertTrue(any("vendor-runtime-path" in finding for finding in findings))

    def test_repository_adapters_are_exact_pointers(self) -> None:
        self.assertEqual(GUARD.check_adapters(), [])

    def test_adapter_shape_rejects_embedded_workflow(self) -> None:
        path = "CLAUDE.md"
        original = GUARD.ADAPTER_CONTENT[path]
        GUARD.ADAPTER_CONTENT[path] = original + "Run a host workflow.\n"
        try:
            findings = GUARD.check_adapters()
        finally:
            GUARD.ADAPTER_CONTENT[path] = original
        self.assertTrue(any("adapter-shape" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
