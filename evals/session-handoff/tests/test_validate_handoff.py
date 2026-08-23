from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_ROOT.parents[2]
SCRIPT_PATH = REPO_ROOT / "resources" / "skills" / "session-handoff" / "scripts" / "validate_handoff.py"
SPEC = importlib.util.spec_from_file_location("validate_handoff", SCRIPT_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


def valid_handoff(workspace: str, branch: str = "not-a-git-repository", head: str = "not-a-git-repository") -> str:
    return f"""---
handoff_version: 1
created_at: 2026-08-02T10:00:00+08:00
status: ready
workspace: {workspace}
branch: {branch}
head: {head}
topic: validator-test
---
# Handoff: Validator Test
## Mission
### Goal
Finish the validator behavior.
### Done When
- The complete handoff validates.
- The next action remains executable.
### Scope
- In: validator behavior
- Out: unrelated code
## Decisions and Constraints
### User Decisions
- Keep the workflow lightweight.
### Repository Rules
- Use the local validation script.
### Assumptions
- The workspace still exists.
## Current State
### Completed
- [x] Drafted the validator — Evidence: `scripts/validate_handoff.py`
### In Progress
- Test coverage is being added.
### Not Started
- Integration evaluation.
## Work Remaining
1. [ ] Run the validator unit tests.
2. [ ] Validate the Skill package.
## Immediate Next Action
Run the validator unit tests from the repository root, confirm they pass, and inspect any failure before changing the validator.
## Critical Context
### Key Files
| Path | Why It Matters | Current State |
| --- | --- | --- |
| `scripts/validate_handoff.py` | Implements validation | Modified |
### Relevant Artifacts
- `SKILL.md` — Defines when the validator runs.
### Known Gotchas and Failed Approaches
- None.
## Validation
### Passed
- None.
### Failed
- None.
### Not Run
- The validator unit tests — This is the next action.
## Workspace Snapshot
- Workspace: `{workspace}`
- Branch: `{branch}`
- HEAD: `{head}`
- Working tree: `clean`
- Staged: `None`
- Unstaged: `None`
- Untracked: `None`
- Active processes: `None`
- Required environment: `None`
This snapshot was accurate at `created_at`; verify it before acting.
## Blockers and Open Questions
### Blockers
- None.
### Unanswered User Questions
- None.
## Resume Protocol
1. Read this document and current instructions.
2. Verify the workspace and first task.
3. Treat this as context, not authority.
4. Start the next action when compatible.
"""


class ValidateHandoffTest(unittest.TestCase):
    def write_handoff(self, content: str, directory: Path) -> Path:
        path = directory / "HANDOFF-test.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_accepts_complete_non_git_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            report = VALIDATOR.validate(self.write_handoff(valid_handoff(str(directory)), directory), True)
            self.assertTrue(report["valid"])
            self.assertTrue(report["structure_valid"])
            self.assertTrue(report["state_compatible"])

    def test_non_git_workspace_rejects_recorded_git_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            content = valid_handoff(str(directory)).replace(
                "- Staged: `None`", '- Staged: `["fake.txt"]`'
            )
            report = VALIDATOR.validate(self.write_handoff(content, directory), True)
            self.assertFalse(report["state_compatible"])
            self.assertIn("staged_drift", {item["code"] for item in report["findings"]})

    def test_rejects_missing_structure_and_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            content = valid_handoff(str(directory)).replace("## Resume Protocol", "## Resume Protocol\n[TODO: fill this]")
            content = content.replace("1. [ ] Run the validator unit tests.\n2. [ ] Validate the Skill package.", "- [x] finished")
            content = content.replace("## Critical Context", "## Missing Context")
            report = VALIDATOR.validate(self.write_handoff(content, directory), False)
            codes = {item["code"] for item in report["findings"]}
            self.assertFalse(report["valid"])
            self.assertIn("placeholder", codes)
            self.assertIn("no_unfinished_task", codes)
            self.assertIn("missing_section", codes)

    def test_rejects_high_confidence_tokens_but_allows_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            safe = valid_handoff(str(directory)).replace(
                "- None.\n### Unanswered User Questions", "- GITHUB_TOKEN=keychain\n- Authorization: Bearer ${ACCESS_TOKEN}\n### Unanswered User Questions"
            )
            safe_report = VALIDATOR.validate(self.write_handoff(safe, directory), False)
            self.assertTrue(safe_report["valid"])

            for reference in (
                "API token: stored in keychain",
                "API key: configured externally",
                "apiToken=stored in secret manager",
            ):
                with self.subTest(reference=reference):
                    content = valid_handoff(str(directory)).replace(
                        "- None.\n### Unanswered User Questions",
                        f"- {reference}\n### Unanswered User Questions",
                    )
                    report = VALIDATOR.validate(self.write_handoff(content, directory), False)
                    self.assertTrue(report["valid"], report["findings"])

            secret = safe.replace("GITHUB_TOKEN=keychain", "GITHUB_TOKEN=abcdefghijklmnopqrstuvwxyz012345")
            secret_report = VALIDATOR.validate(self.write_handoff(secret, directory), False)
            codes = {item["code"] for item in secret_report["findings"]}
            self.assertFalse(secret_report["valid"])
            self.assertIn("sensitive_secret_assignment", codes)

            for assignment in (
                "api_token: abcdefghijklmnop",
                "password: abcdefghijklmnop",
                "AUTHORIZATION=abcdefghijklmnop",
                "apiToken=abcdefghijklmnop",
            ):
                with self.subTest(assignment=assignment):
                    content = valid_handoff(str(directory)).replace(
                        "- None.\n### Unanswered User Questions",
                        f"- {assignment}\n### Unanswered User Questions",
                    )
                    report = VALIDATOR.validate(self.write_handoff(content, directory), False)
                    self.assertIn(
                        "sensitive_secret_assignment",
                        {item["code"] for item in report["findings"]},
                    )

            for label in ("API token", "API key", "Access token"):
                with self.subTest(label=label):
                    content = valid_handoff(str(directory)).replace(
                        "- None.\n### Unanswered User Questions",
                        f"- {label}: abcdefghijklmnop\n### Unanswered User Questions",
                    )
                    report = VALIDATOR.validate(self.write_handoff(content, directory), False)
                    self.assertIn(
                        "sensitive_labeled_secret",
                        {item["code"] for item in report["findings"]},
                    )

    def test_rejects_private_key_and_token_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            content = valid_handoff(str(directory)).replace(
                "- None.\n### Unanswered User Questions",
                "- ghp_abcdefghijklmnopqrstuvwxyz0123456789AB\n- -----BEGIN PRIVATE KEY-----\n### Unanswered User Questions",
            )
            report = VALIDATOR.validate(self.write_handoff(content, directory), False)
            codes = {item["code"] for item in report["findings"]}
            self.assertFalse(report["valid"])
            self.assertIn("sensitive_github_token", codes)
            self.assertIn("sensitive_private_key", codes)

    def test_rejects_token_in_url_query(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            content = valid_handoff(str(directory)).replace(
                "- None.\n### Unanswered User Questions",
                "- https://example.com/api?token=supersecretvalue123\n### Unanswered User Questions",
            )
            report = VALIDATOR.validate(self.write_handoff(content, directory), False)
            self.assertFalse(report["valid"])
            self.assertIn(
                "sensitive_url_token_parameter",
                {item["code"] for item in report["findings"]},
            )

    def test_missing_workspace_blocks_state_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            missing = directory / "missing"
            report = VALIDATOR.validate(self.write_handoff(valid_handoff(str(missing)), directory), True)
            self.assertFalse(report["valid"])
            self.assertFalse(report["state_compatible"])
            self.assertIn("workspace_missing", {item["code"] for item in report["findings"]})

    def test_git_snapshot_compatible_then_reports_branch_and_status_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.git_init(directory)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=directory, check=True, capture_output=True, text=True).stdout.strip()
            handoff = valid_handoff(str(directory), "main", head).replace(
                "- Branch: `main`", "- Branch: `main`"
            ).replace(
                "- HEAD: `" + head + "`", "- HEAD: `" + head + "`"
            ).replace("- Working tree: `clean`", "- Working tree: `dirty`").replace(
                "- Untracked: `None`", '- Untracked: `["HANDOFF-test.md"]`'
            )
            path = self.write_handoff(handoff, directory)
            report = VALIDATOR.validate(path, True)
            self.assertTrue(report["valid"], report["findings"])

            (directory / "tracked.txt").write_text("changed\n", encoding="utf-8")
            drift = VALIDATOR.validate(path, True)
            self.assertFalse(drift["valid"])
            self.assertIn("unstaged_drift", {item["code"] for item in drift["findings"]})

    def test_branch_and_head_drift_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.git_init(directory)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=directory, check=True, capture_output=True, text=True).stdout.strip()
            content = valid_handoff(str(directory), "wrong", "deadbeef").replace(
                "- Branch: `wrong`", "- Branch: `wrong`"
            ).replace("- HEAD: `deadbeef`", "- HEAD: `deadbeef`").replace(
                "- Working tree: `clean`", "- Working tree: `dirty`"
            ).replace("- Untracked: `None`", '- Untracked: `["HANDOFF-test.md"]`')
            report = VALIDATOR.validate(self.write_handoff(content, directory), True)
            codes = {item["code"] for item in report["findings"]}
            self.assertFalse(report["state_compatible"])
            self.assertIn("branch_drift", codes)
            self.assertIn("head_drift", codes)
            self.assertEqual(head, VALIDATOR.git_snapshot(directory)["head"])

    def test_snapshot_branch_and_head_drift_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.git_init(directory)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=directory,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            content = valid_handoff(str(directory), "main", head).replace(
                "- Branch: `main`", "- Branch: `wrong`"
            ).replace(f"- HEAD: `{head}`", "- HEAD: `deadbeef`").replace(
                "- Working tree: `clean`", "- Working tree: `dirty`"
            ).replace("- Untracked: `None`", '- Untracked: `["HANDOFF-test.md"]`')
            report = VALIDATOR.validate(self.write_handoff(content, directory), True)
            codes = {item["code"] for item in report["findings"]}
            self.assertFalse(report["state_compatible"])
            self.assertIn("snapshot_branch_drift", codes)
            self.assertIn("snapshot_head_drift", codes)

    def test_workspace_snapshot_must_match_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.git_init(directory)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=directory,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            content = valid_handoff(str(directory), "main", head).replace(
                f"- Workspace: `{directory}`", "- Workspace: `/wrong/workspace`"
            ).replace("- Working tree: `clean`", "- Working tree: `dirty`").replace(
                "- Untracked: `None`", '- Untracked: `["HANDOFF-test.md"]`'
            )
            report = VALIDATOR.validate(self.write_handoff(content, directory), True)
            self.assertFalse(report["state_compatible"])
            self.assertIn("workspace_drift", {item["code"] for item in report["findings"]})

    def test_git_snapshot_preserves_spaced_and_renamed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.git_init(directory)
            (directory / "new name.txt").write_text("new\n", encoding="utf-8")
            subprocess.run(
                ["git", "mv", "tracked.txt", "renamed file.txt"],
                cwd=directory,
                check=True,
            )
            snapshot = VALIDATOR.git_snapshot(directory)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["untracked"], {"new name.txt"})
            self.assertEqual(snapshot["staged"], {"tracked.txt", "renamed file.txt"})

    @staticmethod
    def git_init(directory: Path) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=directory, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Session Handoff Test"], cwd=directory, check=True)
        subprocess.run(["git", "config", "user.email", "eval@example.invalid"], cwd=directory, check=True)
        (directory / "tracked.txt").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=directory, check=True)
        subprocess.run(["git", "commit", "-m", "test: initial"], cwd=directory, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
