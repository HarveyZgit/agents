#!/usr/bin/env python3
"""Self-tests for the rules-sync eval sandbox builder.

The guards matter more than the happy path: this script takes a directory it
will delete and repopulate, so a mistaken target must be refused rather than
merged into.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "setup_sandbox.py"
SPEC = importlib.util.spec_from_file_location("setup_sandbox", SCRIPT_PATH)
assert SPEC and SPEC.loader
SETUP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SETUP
SPEC.loader.exec_module(SETUP)


class SandboxGuardTest(unittest.TestCase):
    def test_refuses_target_outside_temporary_roots(self) -> None:
        with self.assertRaises(ValueError):
            SETUP.prepare_target(SETUP.REPO_ROOT / "sandbox", replace=False)

    def test_refuses_home_and_temp_root_themselves(self) -> None:
        for target in (Path.home(), Path(tempfile.gettempdir())):
            with self.assertRaises(ValueError):
                SETUP.prepare_target(target, replace=True)

    def test_refuses_existing_directory_without_marker(self) -> None:
        with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as temporary:
            target = Path(temporary) / "sandbox"
            target.mkdir()
            (target / "important.txt").write_text("keep me\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                SETUP.prepare_target(target, replace=True)
            self.assertTrue((target / "important.txt").exists())

    def test_replaces_only_marked_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as temporary:
            target = Path(temporary) / "sandbox"
            target.mkdir()
            (target / SETUP.MARKER_NAME).write_text(SETUP.MARKER_TEXT, encoding="utf-8")
            (target / "stale.txt").write_text("drop me\n", encoding="utf-8")
            SETUP.prepare_target(target, replace=True)
            self.assertFalse(target.exists())


class SandboxLayoutTest(unittest.TestCase):
    def test_fresh_scenario_seeds_every_host_without_installing(self) -> None:
        original_home = os.environ.get("HOME")
        with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as temporary:
            target = Path(temporary) / "sandbox"
            try:
                SETUP.build(target, "fresh")
                adapter = SETUP.load_adapter()
                for host in adapter.HOSTS:
                    self.assertTrue(
                        adapter.host_path(host.detect).is_dir(),
                        f"{host.key} was not seeded",
                    )
                self.assertFalse(adapter.receipt_path().exists())
            finally:
                if original_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = original_home


if __name__ == "__main__":
    unittest.main()
