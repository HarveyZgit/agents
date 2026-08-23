#!/usr/bin/env python3
"""Self-tests for the rules-sync adapter's edit primitives.

These cover the operations that touch files a user owns: inserting and removing
a managed block, registering and deregistering a config entry, and remembering
which files we created. A regression here silently damages host configuration,
which is exactly what the receipt and the markers exist to prevent.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ADAPTER_PATH = REPO_ROOT / "skills" / "rules-sync" / "scripts" / "sync_rules.py"
SPEC = importlib.util.spec_from_file_location("rules_sync_adapter", ADAPTER_PATH)
assert SPEC and SPEC.loader
ADAPTER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ADAPTER
SPEC.loader.exec_module(ADAPTER)

FRAGMENT = """---
name: example-rule
description: Example.
tier: core
---

## Example rule

- Do the thing.
"""


@contextlib.contextmanager
def store_at(path: Path):
    """Point the adapter's fragment store at a throwaway directory."""
    original = os.environ.get("AGENT_RULES_HOME")
    os.environ["AGENT_RULES_HOME"] = str(path)
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("AGENT_RULES_HOME", None)
        else:
            os.environ["AGENT_RULES_HOME"] = original


def fragment(name: str) -> object:
    return ADAPTER.Fragment(
        name=name, filename=f"{name}.md", description="", tier="core", body=f"## {name}"
    )


class FragmentParsingTest(unittest.TestCase):
    def test_frontmatter_is_metadata_and_never_reaches_the_body(self) -> None:
        fragment = ADAPTER.parse_fragment("example-rule.md", FRAGMENT)
        self.assertIsNotNone(fragment)
        self.assertEqual(fragment.name, "example-rule")
        self.assertEqual(fragment.tier, "core")
        self.assertTrue(fragment.body.startswith("## Example rule"))
        self.assertNotIn("tier:", fragment.body)

    def test_documentation_without_frontmatter_is_not_a_fragment(self) -> None:
        self.assertIsNone(ADAPTER.parse_fragment("README.md", "# rules\n\nNotes.\n"))

    def test_frontmatter_without_required_keys_is_rejected(self) -> None:
        self.assertIsNone(
            ADAPTER.parse_fragment("x.md", "---\ndescription: no name\n---\n\n## X\n\n- y\n")
        )


class ManagedBlockTest(unittest.TestCase):
    def test_block_is_appended_then_replaced_in_place(self) -> None:
        original = "# Global notes\n\n- Keep answers short.\n"
        first = ADAPTER.replace_block(original, "BEGIN_A")
        self.assertTrue(first.startswith(original.rstrip("\n")))
        self.assertIn("BEGIN_A", first)

        block = f"{ADAPTER.BEGIN_MARKER}\nold\n{ADAPTER.END_MARKER}"
        wrapped = ADAPTER.replace_block(original, block)
        replacement = f"{ADAPTER.BEGIN_MARKER}\nnew\n{ADAPTER.END_MARKER}"
        updated = ADAPTER.replace_block(wrapped, replacement)
        self.assertIn("new", updated)
        self.assertNotIn("old", updated)
        self.assertEqual(updated.count(ADAPTER.BEGIN_MARKER), 1)
        self.assertIn("Keep answers short.", updated)

    def test_stripping_the_block_restores_user_content(self) -> None:
        original = "# Global notes\n\n- Keep answers short.\n"
        block = f"{ADAPTER.BEGIN_MARKER}\nmanaged\n{ADAPTER.END_MARKER}"
        wrapped = ADAPTER.replace_block(original, block)
        self.assertEqual(ADAPTER.strip_block(wrapped).rstrip("\n"), original.rstrip("\n"))

    def test_stripping_a_file_we_created_yields_nothing_to_keep(self) -> None:
        block = f"{ADAPTER.BEGIN_MARKER}\nmanaged\n{ADAPTER.END_MARKER}"
        self.assertEqual(ADAPTER.strip_block(ADAPTER.replace_block("", block)), "")

    def test_content_outside_the_block_is_never_touched(self) -> None:
        block = f"{ADAPTER.BEGIN_MARKER}\nmanaged\n{ADAPTER.END_MARKER}"
        document = f"before\n\n{block}\n\nafter\n"
        self.assertEqual(ADAPTER.strip_block(document), "before\nafter\n")

    def test_a_block_at_the_start_leaves_no_leading_blank_line(self) -> None:
        block = f"{ADAPTER.BEGIN_MARKER}\nmanaged\n{ADAPTER.END_MARKER}"
        self.assertEqual(ADAPTER.strip_block(f"{block}\n\nafter\n"), "after\n")

    def test_an_end_marker_in_user_prose_does_not_duplicate_the_block(self) -> None:
        # The marker text can appear in the user's own notes before the managed
        # block; matching that copy would append a new block on every run.
        block = f"{ADAPTER.BEGIN_MARKER}\nold\n{ADAPTER.END_MARKER}"
        document = f"I document the {ADAPTER.END_MARKER} marker here.\n\n{block}\n"
        replacement = f"{ADAPTER.BEGIN_MARKER}\nnew\n{ADAPTER.END_MARKER}"
        updated = ADAPTER.replace_block(document, replacement)
        self.assertEqual(updated.count(ADAPTER.BEGIN_MARKER), 1)
        self.assertIn("new", updated)
        self.assertNotIn("old", updated)
        self.assertNotIn("old", ADAPTER.strip_block(updated))
        self.assertIn("I document the", ADAPTER.strip_block(updated))


class ReceiptTest(unittest.TestCase):
    def test_created_flag_survives_a_second_install(self) -> None:
        previous = [{"path": "/x/AGENTS.md", "kind": "block", "created": True}]
        current = [{"path": "/x/AGENTS.md", "kind": "block", "created": False}]
        self.assertTrue(ADAPTER.merge_artifacts(previous, current)[0]["created"])

    def test_artifacts_absent_from_this_run_are_still_remembered(self) -> None:
        # Dropping them would leave whatever they name unreverted by uninstall.
        previous = [{"path": "/x/old.md", "kind": "symlink"}]
        current = [{"path": "/x/new.md", "kind": "symlink"}]
        paths = [item["path"] for item in ADAPTER.merge_artifacts(previous, current)]
        self.assertEqual(paths, ["/x/new.md", "/x/old.md"])

    def test_retired_artifacts_are_forgotten(self) -> None:
        previous = [{"path": "/x/old.md", "kind": "symlink"}]
        merged = ADAPTER.merge_artifacts(previous, [], {"/x/old.md"})
        self.assertEqual(merged, [])

    def test_structurally_broken_receipt_stops_with_the_same_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "rules"
            store.mkdir()
            (store / ADAPTER.RECEIPT_NAME).write_text(
                json.dumps({"hosts": {"codex": {"artifacts": [{"kind": "block"}]}}}),
                encoding="utf-8",
            )
            with store_at(store):
                with self.assertRaises(SystemExit):
                    ADAPTER.read_receipt()

    def test_unreadable_receipt_stops_instead_of_reporting_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "rules"
            store.mkdir()
            (store / ADAPTER.RECEIPT_NAME).write_text("{ not json", encoding="utf-8")
            with store_at(store):
                with self.assertRaises(SystemExit):
                    ADAPTER.read_receipt()


class ConfigHostTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.original_store = os.environ.get("AGENT_RULES_HOME")
        os.environ["AGENT_RULES_HOME"] = str(root / "store")
        self.addCleanup(self.restore_store)
        self.host = next(host for host in ADAPTER.HOSTS if host.mode == "config")
        self.config = root / "config.json"

    def restore_store(self) -> None:
        if self.original_store is None:
            os.environ.pop("AGENT_RULES_HOME", None)
        else:
            os.environ["AGENT_RULES_HOME"] = self.original_store

    def plan_against(self, target: Path, alternate: Path | None = None):
        host = ADAPTER.Host(
            key=self.host.key,
            label=self.host.label,
            mode=self.host.mode,
            detect=self.host.detect,
            target=str(target),
            alt_target=str(alternate) if alternate else "",
        )
        return ADAPTER.plan_config(host)

    def test_registering_preserves_unrelated_keys_and_entries(self) -> None:
        self.config.write_text(
            json.dumps({"theme": "dark", "instructions": ["docs/own.md"]}) + "\n",
            encoding="utf-8",
        )
        actions = self.plan_against(self.config)
        actions[0].apply()
        result = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(result["theme"], "dark")
        self.assertIn("docs/own.md", result["instructions"])
        self.assertIn(ADAPTER.config_glob(), result["instructions"])

    def test_registering_twice_adds_one_entry(self) -> None:
        self.config.write_text(json.dumps({}) + "\n", encoding="utf-8")
        self.plan_against(self.config)[0].apply()
        self.assertIsNone(self.plan_against(self.config)[0].apply)
        result = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(result["instructions"].count(ADAPTER.config_glob()), 1)

    def test_deregistering_leaves_the_users_own_entries(self) -> None:
        self.config.write_text(
            json.dumps({"theme": "dark", "instructions": ["docs/own.md"]}) + "\n",
            encoding="utf-8",
        )
        self.plan_against(self.config)[0].apply()
        ADAPTER.undo_artifact({"path": str(self.config), "kind": "config", "created": False})
        result = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(result["instructions"], ["docs/own.md"])
        self.assertEqual(result["theme"], "dark")

    def test_the_alternate_spelling_is_not_shadowed_by_a_new_thin_file(self) -> None:
        # The host reads either spelling; creating the second one would leave two
        # configs whose precedence it does not document.
        alternate = self.config.with_suffix(".jsonc")
        alternate.write_text('{\n  // mine\n  "theme": "dark"\n}\n', encoding="utf-8")
        actions = self.plan_against(self.config, alternate)
        self.assertTrue(actions[0].conflict)
        self.assertIn("JSONC", actions[0].conflict)
        self.assertIn(ADAPTER.config_glob(), actions[0].conflict)
        self.assertFalse(self.config.exists())

    def test_a_glob_already_present_in_the_alternate_is_accepted(self) -> None:
        alternate = self.config.with_suffix(".jsonc")
        alternate.write_text(
            '{\n  // mine\n  "instructions": ["%s"]\n}\n' % ADAPTER.config_glob(),
            encoding="utf-8",
        )
        actions = self.plan_against(self.config, alternate)
        self.assertFalse(actions[0].conflict)
        self.assertIsNone(actions[0].apply)

    def test_both_spellings_present_is_refused(self) -> None:
        alternate = self.config.with_suffix(".jsonc")
        alternate.write_text("{}\n", encoding="utf-8")
        self.config.write_text("{}\n", encoding="utf-8")
        actions = self.plan_against(self.config, alternate)
        self.assertTrue(actions[0].conflict)
        self.assertIn("both exist", actions[0].conflict)

    def test_non_list_instructions_is_refused_rather_than_iterated(self) -> None:
        self.config.write_text(
            json.dumps({"instructions": "docs/own.md"}) + "\n", encoding="utf-8"
        )
        with self.assertRaises(SystemExit):
            self.plan_against(self.config)


class ForeignCopyTest(unittest.TestCase):
    """Another tool may already publish these fragments under its own markers."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fragments = [fragment("alpha")]
        template = next(host for host in ADAPTER.HOSTS if host.mode == "inline")
        self.path = Path(self.temporary.name) / "AGENTS.md"
        self.host = ADAPTER.Host(
            key=template.key,
            label=template.label,
            mode=template.mode,
            detect=template.detect,
            target=str(self.path),
        )

    def test_a_copy_outside_our_block_is_detected(self) -> None:
        document = "# Theirs\n\n<!-- BEGIN other-tool -->\n## alpha\n<!-- END other-tool -->\n"
        self.assertEqual(ADAPTER.foreign_copies(document, self.fragments), ["## alpha"])

    def test_our_own_block_is_not_mistaken_for_a_copy(self) -> None:
        block = ADAPTER.render_block(self.host, self.fragments, "main")
        self.assertEqual(ADAPTER.foreign_copies(ADAPTER.replace_block("", block), self.fragments), [])

    def test_an_unrelated_file_is_clean(self) -> None:
        self.assertEqual(ADAPTER.foreign_copies("# Notes\n\n- Be brief.\n", self.fragments), [])

    def test_planning_refuses_instead_of_appending_a_second_copy(self) -> None:
        original = "<!-- BEGIN other-tool -->\n## alpha\n<!-- END other-tool -->\n"
        self.path.write_text(original, encoding="utf-8")
        actions = ADAPTER.plan_block(self.host, self.fragments, "main")
        self.assertTrue(actions[0].conflict)
        self.assertIsNone(actions[0].apply)
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)


class LinkHostTest(unittest.TestCase):
    """The link mode is the only one that leaves files a host enumerates itself."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.store = root / "store"
        self.store.mkdir()
        self.target = root / "rules"
        self.target.mkdir()
        context = store_at(self.store)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        template = next(host for host in ADAPTER.HOSTS if host.mode == "link")
        self.host = ADAPTER.Host(
            key=template.key,
            label=template.label,
            mode=template.mode,
            detect=template.detect,
            target=str(self.target),
        )

    def test_a_withdrawn_fragment_leaves_no_dangling_link(self) -> None:
        (self.target / "beta.md").symlink_to(self.store / "beta.md")
        actions = ADAPTER.plan_link(self.host, [fragment("alpha")])
        retiring = [action for action in actions if action.retires]
        self.assertEqual(len(retiring), 1)
        for action in actions:
            if action.apply is not None:
                action.apply()
        self.assertFalse((self.target / "beta.md").is_symlink())
        self.assertEqual(retiring[0].retires, str(self.target / "beta.md"))

    def test_links_to_another_store_are_named_in_the_host_list(self) -> None:
        theirs = Path(self.temporary.name) / "their-store"
        theirs.mkdir()
        (self.target / "alpha.md").symlink_to(theirs / "alpha.md")
        state = ADAPTER.observed_state(self.host, [fragment("alpha")])
        self.assertIn(str(theirs), state)

    def test_a_foreign_link_in_the_directory_is_left_alone(self) -> None:
        elsewhere = Path(self.temporary.name) / "elsewhere.md"
        elsewhere.write_text("theirs\n", encoding="utf-8")
        (self.target / "theirs.md").symlink_to(elsewhere)
        actions = ADAPTER.plan_link(self.host, [fragment("alpha")])
        self.assertEqual([action for action in actions if action.retires], [])

    def test_a_file_where_the_directory_belongs_is_a_conflict(self) -> None:
        occupied = Path(self.temporary.name) / "occupied"
        occupied.write_text("stray\n", encoding="utf-8")
        host = ADAPTER.Host(
            key=self.host.key,
            label=self.host.label,
            mode=self.host.mode,
            detect=self.host.detect,
            target=str(occupied),
        )
        actions = ADAPTER.plan_link(host, [fragment("alpha")])
        self.assertTrue(actions[0].conflict)
        self.assertEqual(occupied.read_text(encoding="utf-8"), "stray\n")

    def test_a_real_file_in_the_way_is_reported_as_a_conflict_not_an_abort(self) -> None:
        (self.target / "alpha.md").write_text("mine\n", encoding="utf-8")
        actions = ADAPTER.plan_link(self.host, [fragment("alpha")])
        self.assertTrue(actions[0].conflict)
        self.assertIsNone(actions[0].apply)
        self.assertEqual((self.target / "alpha.md").read_text(encoding="utf-8"), "mine\n")


class UndoArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "AGENTS.md"
        self.block = f"{ADAPTER.BEGIN_MARKER}\nmanaged\n{ADAPTER.END_MARKER}"

    def test_a_file_we_created_is_deleted(self) -> None:
        self.path.write_text(ADAPTER.replace_block("", self.block), encoding="utf-8")
        ADAPTER.undo_artifact({"path": str(self.path), "kind": "block", "created": True})
        self.assertFalse(self.path.exists())

    def test_a_file_the_user_owned_keeps_their_content(self) -> None:
        original = "# Mine\n\n- Keep this.\n"
        self.path.write_text(ADAPTER.replace_block(original, self.block), encoding="utf-8")
        ADAPTER.undo_artifact({"path": str(self.path), "kind": "block", "created": False})
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)


class WriteThroughSymlinkTest(unittest.TestCase):
    def test_symlinked_host_config_keeps_its_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "dotfiles" / "AGENTS.md"
            real.parent.mkdir()
            real.write_text("original\n", encoding="utf-8")
            link = root / "AGENTS.md"
            link.symlink_to(real)
            ADAPTER.write_file(link, "updated\n")
            self.assertTrue(link.is_symlink())
            self.assertEqual(real.read_text(encoding="utf-8"), "updated\n")

    def test_restricted_permissions_survive_a_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "opencode.json"
            path.write_text("{}\n", encoding="utf-8")
            path.chmod(0o600)
            ADAPTER.write_file(path, '{"instructions": []}\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
