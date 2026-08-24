#!/usr/bin/env python3
"""Self-tests for the rules-sync adapter's edit primitives.

These cover the operations that touch files a user owns: inserting and removing
a managed block, registering and deregistering a config entry, writing host-owned
.mdc files, and remembering which files we created. A regression here silently
damages host configuration, which is exactly what the receipt and the markers
exist to prevent.
"""

from __future__ import annotations

import contextlib
import io
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


class ResolveCommitTest(unittest.TestCase):
    def test_a_commit_needs_no_lookup(self) -> None:
        sha = "0" * 40
        self.assertEqual(ADAPTER.resolve_commit(sha), sha)


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


class MdcHostTest(unittest.TestCase):
    """The mdc mode writes one host-owned .mdc file per fragment."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.home = root / "home"
        self.home.mkdir()
        self.store = root / "store"
        self.store.mkdir()
        self.original_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self.restore_home)
        context = store_at(self.store)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        template = ADAPTER.HOSTS_BY_KEY["cursor"]
        self.host = ADAPTER.Host(
            key=template.key,
            label=template.label,
            mode=template.mode,
            detect=template.detect,
            target=str(root / "rules"),
            note=template.note,
        )

    def restore_home(self) -> None:
        if self.original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.original_home

    def make_fragment(self, name: str, description: str = "Example.") -> object:
        return ADAPTER.Fragment(
            name=name,
            filename=f"{name}.md",
            description=description,
            tier="core",
            body=f"## {name}\n\n- Do the thing.",
        )

    def apply(self, actions) -> None:
        for action in actions:
            if action.apply is not None:
                action.apply()

    def test_hosts_table_wires_cursor_as_mdc(self) -> None:
        host = ADAPTER.HOSTS_BY_KEY["cursor"]
        self.assertEqual(host.label, "Cursor CLI")
        self.assertEqual(host.mode, "mdc")
        self.assertEqual(host.target, "~/.cursor/rules")
        self.assertEqual([item.key for item in ADAPTER.HOSTS if item.mode == "manual"], [])

    def test_install_writes_mdc_with_always_apply_and_body(self) -> None:
        fragment = self.make_fragment("example-rule")
        actions = ADAPTER.plan_host(self.host, [fragment], "main")
        self.assertFalse(any(action.conflict for action in actions))
        self.apply(actions)
        path = Path(self.host.target) / "example-rule.mdc"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(
            text,
            "---\ndescription: Example.\nalwaysApply: true\n---\n\n"
            "## example-rule\n\n- Do the thing.\n",
        )
        self.assertEqual(actions[0].artifact["kind"], "file")

    def test_install_creates_the_target_directory(self) -> None:
        target = Path(self.host.target)
        self.assertFalse(target.exists())
        self.apply(ADAPTER.plan_mdc(self.host, [self.make_fragment("alpha")]))
        self.assertTrue((target / "alpha.mdc").is_file())

    def test_matching_content_is_current(self) -> None:
        fragment = self.make_fragment("alpha")
        self.apply(ADAPTER.plan_mdc(self.host, [fragment]))
        actions = ADAPTER.plan_mdc(self.host, [fragment])
        self.assertEqual(len(actions), 1)
        self.assertIsNone(actions[0].apply)
        self.assertFalse(actions[0].conflict)

    def test_update_rewrites_a_managed_file_when_the_body_changes(self) -> None:
        first = self.make_fragment("alpha", "First.")
        self.apply(ADAPTER.plan_mdc(self.host, [first]))
        second = ADAPTER.Fragment(
            name="alpha",
            filename="alpha.md",
            description="Second.",
            tier="core",
            body="## alpha\n\n- Do the other thing.",
        )
        actions = ADAPTER.plan_mdc(self.host, [second])
        self.assertIsNotNone(actions[0].apply)
        self.apply(actions)
        text = (Path(self.host.target) / "alpha.mdc").read_text(encoding="utf-8")
        self.assertIn("description: Second.", text)
        self.assertIn("- Do the other thing.", text)
        self.assertNotIn("- Do the thing.", text)

    def test_empty_store_description_does_not_look_like_drift(self) -> None:
        # check rebuilds fragments from the store, which has no description.
        self.apply(ADAPTER.plan_mdc(self.host, [self.make_fragment("alpha", "Example.")]))
        stored = ADAPTER.Fragment(
            name="alpha", filename="alpha.md", description="", tier="core",
            body="## alpha\n\n- Do the thing.",
        )
        actions = ADAPTER.plan_mdc(self.host, [stored])
        self.assertIsNone(actions[0].apply)
        self.assertIn("description: Example.", (Path(self.host.target) / "alpha.mdc").read_text(encoding="utf-8"))

    def test_a_foreign_file_with_the_same_name_is_a_conflict(self) -> None:
        path = Path(self.host.target)
        path.mkdir()
        occupied = path / "alpha.mdc"
        occupied.write_text("# mine\n\n- keep this\n", encoding="utf-8")
        actions = ADAPTER.plan_mdc(self.host, [self.make_fragment("alpha")])
        self.assertTrue(actions[0].conflict)
        self.assertIsNone(actions[0].apply)
        self.assertEqual(occupied.read_text(encoding="utf-8"), "# mine\n\n- keep this\n")

    def test_uninstall_removes_only_our_files(self) -> None:
        target = Path(self.host.target)
        self.apply(ADAPTER.plan_mdc(self.host, [self.make_fragment("alpha")]))
        theirs = target / "personal.mdc"
        theirs.write_text("---\nalwaysApply: true\n---\n\n# mine\n", encoding="utf-8")
        ours = target / "alpha.mdc"
        ADAPTER.undo_artifact({"path": str(ours), "kind": "file", "created": True})
        self.assertFalse(ours.exists())
        self.assertEqual(theirs.read_text(encoding="utf-8"), "---\nalwaysApply: true\n---\n\n# mine\n")

    def test_withdrawn_managed_file_is_removed_foreign_file_is_not(self) -> None:
        target = Path(self.host.target)
        self.apply(
            ADAPTER.plan_mdc(
                self.host, [self.make_fragment("alpha"), self.make_fragment("beta")]
            )
        )
        theirs = target / "personal.mdc"
        theirs.write_text("---\ndescription: mine\nalwaysApply: true\n---\n\n# mine\n", encoding="utf-8")
        actions = ADAPTER.plan_mdc(
            self.host, [self.make_fragment("alpha")], previous_names={"alpha", "beta"}
        )
        retiring = [action for action in actions if action.retires]
        self.assertEqual(len(retiring), 1)
        self.assertEqual(retiring[0].retires, str(target / "beta.mdc"))
        self.apply(actions)
        self.assertFalse((target / "beta.mdc").exists())
        self.assertTrue((target / "alpha.mdc").exists())
        self.assertTrue(theirs.exists())

    def test_observed_state_counts_our_mdc_files(self) -> None:
        self.apply(ADAPTER.plan_mdc(self.host, [self.make_fragment("alpha")]))
        (Path(self.host.target) / "personal.mdc").write_text(
            "# not ours\n", encoding="utf-8"
        )
        state = ADAPTER.observed_state(self.host, [self.make_fragment("alpha")])
        self.assertEqual(state, "1 managed .mdc file(s)")

    def test_list_hosts_shows_mdc_and_user_rules_dir(self) -> None:
        with io.StringIO() as buffer:
            with contextlib.redirect_stdout(buffer):
                code = ADAPTER.main(["list-hosts"])
            output = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Cursor CLI", output)
        self.assertIn("cursor", output)
        self.assertRegex(output, r"cursor\s+mdc\b")
        self.assertIn("~/.cursor/rules", output)
        self.assertNotIn("(host UI field)", output)

    def test_real_cursor_host_writes_under_sandboxed_home(self) -> None:
        host = ADAPTER.HOSTS_BY_KEY["cursor"]
        fragment = self.make_fragment("example-rule")
        actions = ADAPTER.plan_host(host, [fragment], "main")
        self.apply(actions)
        path = self.home / ".cursor" / "rules" / "example-rule.mdc"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("alwaysApply: true", text.split("\n---\n", 1)[0])
        self.assertIn("## example-rule", text)


if __name__ == "__main__":
    unittest.main()
