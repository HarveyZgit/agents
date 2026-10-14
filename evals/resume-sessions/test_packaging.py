#!/usr/bin/env python3
"""Validate standalone packages without importing or executing their reader."""
from __future__ import annotations

import ast
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES = ("resume-claude", "resume-codex", "resume-cursor")
RESOURCES = ("scripts/session_reader.py", "references/CORE.md", "references/formats.md", "references/PROVENANCE.md")


class PackagingTests(unittest.TestCase):
    def test_each_skill_is_self_contained_when_copied_alone(self):
        for name in NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                installed = Path(temporary) / name
                shutil.copytree(ROOT / "skills" / name, installed)
                for file in installed.rglob("*"):
                    self.assertFalse(file.is_symlink())
                    if file.suffix != ".md":
                        continue
                    for link in re.findall(r"\]\(([^)]+)\)", file.read_text()):
                        if "://" in link or link.startswith("#"):
                            continue
                        target = (file.parent / link.split("#")[0]).resolve()
                        self.assertTrue(target.is_relative_to(installed), str(target))
                        self.assertTrue(target.is_file(), str(target))
                for resource in RESOURCES:
                    self.assertTrue((installed / resource).is_file())
                ast.parse((installed / "scripts/session_reader.py").read_text())

    def test_copies_are_identical(self):
        for resource in RESOURCES:
            data = (ROOT / "skills" / NAMES[0] / resource).read_bytes()
            for name in NAMES[1:]:
                self.assertEqual(data, (ROOT / "skills" / name / resource).read_bytes(), name + "/" + resource)

    def test_no_implicit_host_or_sibling_contract(self):
        for name in NAMES:
            text = "\n".join(file.read_text() for file in (ROOT / "skills" / name).rglob("*.md"))
            for token in ("$SKILL_DIR", "${SKILL_DIR}", "$ARGUMENTS", "../shared/resume-session", "fresh Grok session", "this Grok session"):
                self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
