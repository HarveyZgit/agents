#!/usr/bin/env python3
"""Create isolated Git workspaces for session-handoff behavior evals."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = EVAL_ROOT / "fixtures"
REPO_ROOT = EVAL_ROOT.parents[2]
MARKER_NAME = ".session-handoff-eval"
GIT_ISOLATION_ARGS = (
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "commit.gpgSign=false",
    "-c",
    "tag.gpgSign=false",
    "-c",
    "core.excludesFile=/dev/null",
)
TRUSTED_TEMP_ROOTS = tuple(
    dict.fromkeys(
        (
            Path("/tmp").absolute(),
            Path("/tmp").resolve(),
            Path(tempfile.gettempdir()).absolute(),
            Path(tempfile.gettempdir()).resolve(),
        )
    )
)


def run(directory: Path, *command: str) -> str:
    normalized_command = command
    if command and command[0] == "git":
        normalized_command = ("git", *GIT_ISOLATION_ARGS, *command[1:])
    result = subprocess.run(
        normalized_command,
        cwd=directory,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def initialize_repository(target: Path, branch: str) -> str:
    run(target, "git", "init", "-b", branch)
    run(target, "git", "config", "--local", "core.hooksPath", "/dev/null")
    run(target, "git", "config", "--local", "commit.gpgSign", "false")
    run(target, "git", "config", "--local", "tag.gpgSign", "false")
    run(target, "git", "config", "--local", "core.excludesFile", "/dev/null")
    run(target, "git", "config", "user.name", "Session Handoff Eval")
    run(target, "git", "config", "user.email", "eval@example.invalid")
    run(target, "git", "add", "-f", ".")
    run(target, "git", "commit", "-m", "test: initialize eval fixture")
    return run(target, "git", "rev-parse", "HEAD")


def write_marker(target: Path) -> None:
    (target / MARKER_NAME).write_text("managed by session-handoff evals\n", encoding="utf-8")


def trusted_temp_root(target: Path) -> Path | None:
    candidates = []
    for root in TRUSTED_TEMP_ROOTS:
        try:
            target.relative_to(root)
        except ValueError:
            continue
        candidates.append(root)
    return max(candidates, key=lambda path: len(path.parts)) if candidates else None


def symlink_component(target: Path, trusted_root: Path) -> Path | None:
    current = trusted_root
    for part in target.relative_to(trusted_root).parts:
        current /= part
        if current.is_symlink():
            return current
    return None


def prepare_target(target: Path, replace: bool) -> None:
    trusted_root = trusted_temp_root(target)
    if trusted_root is None:
        raise ValueError(f"Eval target must be inside a trusted temporary directory: {target}")
    dangerous = {
        Path("/").resolve(),
        Path.home().resolve(),
        Path.cwd().resolve(),
        REPO_ROOT.resolve(),
        *(root.resolve() for root in TRUSTED_TEMP_ROOTS),
    }
    if target.resolve() in dangerous:
        raise ValueError(f"Refusing dangerous eval target: {target}")
    linked_component = symlink_component(target, trusted_root)
    if linked_component is not None:
        raise ValueError(f"Refusing eval target through symlink: {linked_component}")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        return
    if not target.is_dir():
        raise ValueError(f"Refusing non-directory target: {target}")
    marker = target / MARKER_NAME
    if not replace:
        raise ValueError(f"Target already exists; pass --replace only for a managed eval directory: {target}")
    if not marker.is_file() or marker.read_text(encoding="utf-8") != "managed by session-handoff evals\n":
        raise ValueError(f"Refusing to replace directory without the eval marker: {target}")
    shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)


def replace_snapshot_tokens(target: Path, branch: str, head: str) -> None:
    for handoff in target.glob("HANDOFF-*.md"):
        content = handoff.read_text(encoding="utf-8")
        content = content.replace("__EVAL_WORKSPACE__", str(target.resolve()))
        content = content.replace("__EVAL_HEAD__", head)
        content = content.replace("branch: main", f"branch: {branch}", 1)
        content = content.replace("- Branch: `main`", f"- Branch: `{branch}`", 1)
        handoff.write_text(content, encoding="utf-8")


def setup_create(target: Path) -> None:
    shutil.copytree(FIXTURES_DIR / "resume-compatible", target)
    write_marker(target)
    (target / "HANDOFF-export-retry.md").unlink()
    initialize_repository(target, "main")

    source = target / "src" / "retry.ts"
    source.write_text(
        source.read_text(encoding="utf-8") + "\n// Retry behavior is still incomplete.\n",
        encoding="utf-8",
    )
    (target / "notes.txt").write_text(
        "Current focused test has one failure: transient errors are not retried.\n",
        encoding="utf-8",
    )


def setup_compatible(target: Path) -> None:
    shutil.copytree(FIXTURES_DIR / "resume-compatible", target)
    write_marker(target)
    handoff = target / "HANDOFF-export-retry.md"
    handoff_content = handoff.read_text(encoding="utf-8")
    handoff.unlink()
    head = initialize_repository(target, "main")
    handoff.write_text(handoff_content, encoding="utf-8")
    replace_snapshot_tokens(target, "main", head)


def setup_drift(target: Path) -> None:
    shutil.copytree(FIXTURES_DIR / "resume-drift", target)
    write_marker(target)
    handoff = target / "HANDOFF-export-retry.md"
    handoff_content = handoff.read_text(encoding="utf-8")
    handoff.unlink()
    head = initialize_repository(target, "replacement-retry")
    handoff.write_text(handoff_content, encoding="utf-8")
    replace_snapshot_tokens(target, "legacy-retry", head)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("create", "resume-compatible", "resume-drift"))
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help=f"Replace an existing directory only when it contains the {MARKER_NAME} marker.",
    )
    args = parser.parse_args()

    expanded_target = args.target.expanduser()
    if ".." in expanded_target.parts:
        parser.error(f"Refusing eval target with '..' path components: {expanded_target}")
    target = expanded_target.absolute()
    try:
        prepare_target(target, args.replace)
    except ValueError as error:
        parser.error(str(error))

    if args.scenario == "create":
        setup_create(target)
    elif args.scenario == "resume-compatible":
        setup_compatible(target)
    else:
        setup_drift(target)

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
