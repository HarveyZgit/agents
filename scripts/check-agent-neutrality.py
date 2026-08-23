#!/usr/bin/env python3
"""Reject host-specific coupling in reusable AI assets."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# Platform discovery files are allowed only as removable pointers to the
# host-neutral source assets.
ADAPTER_CONTENT = {
    ".github/copilot-instructions.md": (
        "# Agents instructions\n\nFollow [`AGENTS.md`](../AGENTS.md).\n"
    ),
    "CLAUDE.md": "# Claude instructions\n\nFollow [AGENTS.md](AGENTS.md).\n",
    "CODEX.md": "# Codex instructions\n\nFollow [AGENTS.md](AGENTS.md).\n",
}

# Reusable Skills are the source of truth. The additional files below define
# their repository policy or installation boundary.
SCAN_PREFIXES = (
    "evals/",
    "rules/",
    "skills/",
)
SCAN_FILES = {
    "AGENTS.md",
    "README.md",
}
# Distributing rules into host configurations requires naming hosts and their
# runtime paths. This file is the adapter layer, exempt by the same logic as
# ADAPTER_CONTENT above. The exemption is per file, so the Skill body shipped
# alongside it stays scanned and must remain host-neutral.
HOST_ADAPTER_FILES = {
    "skills/rules-sync/scripts/sync_rules.py",
}
EXCLUDED_PARTS = {"tests", "fixtures", "workspace", "dist", "node_modules"}
BINARY_SUFFIXES = {".gif", ".ico", ".jpeg", ".jpg", ".mp3", ".mp4", ".otf", ".pdf", ".png", ".ttf", ".wav", ".webp", ".woff", ".woff2", ".zip"}
GUARD_FILES = {"scripts/check-agent-neutrality.py", "scripts/test-agent-neutrality.py"}

RULES = (
    (
        "fixed-agent-identity",
        re.compile(r"TRAE CLI|noreply@bytedance\.com", re.IGNORECASE),
    ),
    (
        "vendor-runtime-path",
        re.compile(
            r"(?:~|\$HOME|/(?:Users|home)/[^/\s]+)/"
            r"(?:\.trae|\.claude|\.codex|\.gemini|\.cursor|\.windsurf)(?:/|$)|"
            r"(?:^|[/\s`\"'])\.(?:trae|claude|codex|gemini|cursor|windsurf)/skills(?:/|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "vendor-tool-invocation",
        re.compile(
            r"\bAgent\s*\(|\bsubagent_type\s*=|\bPreToolUse\b|"
            r"\bPostToolUse\b|\bUserPromptSubmit\b"
        ),
    ),
    (
        "vendor-workflow",
        re.compile(
            r"\b(?:use|run|install|open|requires?|for)"
            r"(?:\s+(?:in|with|for))?\s+(?:the\s+)?"
            r"(?:TRAE|Claude|Codex|Gemini|Cursor)\b|"
            r"\b(?:TRAE|Claude|Codex|Gemini|Cursor)\s+"
            r"(?:agent|CLI|host|IDE|runtime|session|tool|handles?|reviews?|runs?|executes?)\b",
            re.IGNORECASE,
        ),
    ),
)

FIXED_TRAILER = re.compile(
    r"(?:Co-authored-by|Signed-off-by):\s+[^<>\n]+\s+<[^<>\n]+>",
    re.IGNORECASE,
)


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    files = [Path(item.decode()) for item in result.stdout.split(b"\0") if item]
    deleted = subprocess.run(
        ["git", "ls-files", "--deleted", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    deleted_paths = {Path(item.decode()) for item in deleted.stdout.split(b"\0") if item}
    return [path for path in files if path not in deleted_paths]


def should_scan(relative_path: Path) -> bool:
    path = relative_path.as_posix()
    if path in GUARD_FILES or path in ADAPTER_CONTENT or path in HOST_ADAPTER_FILES:
        return False
    if any(part in EXCLUDED_PARTS for part in relative_path.parts):
        return False
    if relative_path.suffix.casefold() in BINARY_SUFFIXES:
        return False
    return path in SCAN_FILES or path.startswith(SCAN_PREFIXES)


def read_repository_text(relative_path: Path) -> str:
    absolute_path = REPO_ROOT / relative_path
    if absolute_path.is_symlink():
        return os.readlink(str(absolute_path))
    return absolute_path.read_text(encoding="utf-8")


def scan_file(relative_path: Path) -> list[str]:
    try:
        text = read_repository_text(relative_path)
    except (OSError, UnicodeError) as error:
        return [f"{relative_path}: [read-error] {error}"]

    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if FIXED_TRAILER.search(line):
            findings.append(
                f"{relative_path}:{line_number}: [fixed-commit-trailer] {line.strip()}"
            )
        for rule_name, pattern in RULES:
            if pattern.search(line):
                findings.append(f"{relative_path}:{line_number}: [{rule_name}] {line.strip()}")
    return findings


def check_adapters() -> list[str]:
    findings: list[str] = []
    for path, expected in ADAPTER_CONTENT.items():
        try:
            actual = read_repository_text(Path(path))
        except (OSError, UnicodeError) as error:
            findings.append(f"{path}: [adapter-read-error] {error}")
            continue
        if actual != expected:
            findings.append(
                f"{path}: [adapter-shape] adapter must exactly match the canonical source pointer"
            )
    return findings


def main() -> int:
    findings = check_adapters()
    for relative_path in repository_files():
        if should_scan(relative_path):
            findings.extend(scan_file(relative_path))

    if findings:
        print("Agent-neutrality violations found:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1

    print("Agent-neutrality check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
