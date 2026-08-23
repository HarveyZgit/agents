from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "setup_eval_workspace.py"


class SetupEvalWorkspaceTest(unittest.TestCase):
    def run_setup(self, scenario: str, target: Path) -> Path:
        result = subprocess.run(
            ["python3", str(SCRIPT), scenario, str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def test_create_workspace_has_uncommitted_task_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = self.run_setup("create", Path(temporary_directory) / "create")
            self.assertTrue((target / ".git").is_dir())
            self.assertTrue((target / "notes.txt").is_file())
            self.assertIn("incomplete", (target / "src/retry.ts").read_text(encoding="utf-8"))
            status = subprocess.run(["git", "status", "--porcelain"], cwd=target, check=True, capture_output=True, text=True).stdout
            self.assertIn("src/retry.ts", status)
            self.assertIn("notes.txt", status)

    def test_resume_compatible_snapshot_has_expected_start_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = self.run_setup("resume-compatible", Path(temporary_directory) / "compatible")
            self.assertTrue((target / "HANDOFF-export-retry.md").is_file())
            self.assertTrue((target / "src/retry.ts").is_file())
            branch = subprocess.run(["git", "branch", "--show-current"], cwd=target, check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, "main")
            status = subprocess.run(["git", "status", "--porcelain"], cwd=target, check=True, capture_output=True, text=True).stdout
            self.assertIn("HANDOFF-export-retry.md", status)

    def test_resume_drift_fixture_has_branch_and_file_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = self.run_setup("resume-drift", Path(temporary_directory) / "drift")
            self.assertTrue((target / "HANDOFF-export-retry.md").is_file())
            self.assertTrue((target / "src/retry-v2.ts").is_file())
            self.assertFalse((target / "src/retry.ts").exists())
            branch = subprocess.run(["git", "branch", "--show-current"], cwd=target, check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, "replacement-retry")


if __name__ == "__main__":
    unittest.main()
