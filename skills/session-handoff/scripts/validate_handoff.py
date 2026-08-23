#!/usr/bin/env python3
"""Validate a handoff's structure, redaction, and optional workspace snapshot."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


REQUIRED_FRONTMATTER = ("handoff_version", "created_at", "status", "workspace", "branch", "head", "topic")
REQUIRED_SECTIONS = ("Mission", "Decisions and Constraints", "Current State", "Work Remaining", "Immediate Next Action", "Critical Context", "Validation", "Workspace Snapshot", "Blockers and Open Questions", "Resume Protocol")
SNAPSHOT_FIELDS = ("Workspace", "Branch", "HEAD", "Working tree", "Staged", "Unstaged", "Untracked")

# Keep this list deliberately small. These patterns identify common credential values;
# ordinary contact details and prose about secrets are not credentials by themselves.
SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("provider_api_key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "secret_assignment",
        re.compile(
            r"(?im)^\s*(?:[-*]\s+)?(?:export\s+|env\s+)?"
            r"(?P<name>(?:[A-Z][A-Z0-9_]*_)?"
            r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|ACCESS_?KEY|COOKIE|"
            r"API_?TOKEN|ACCESS_?TOKEN|AUTH_?TOKEN|AUTHORIZATION))"
            r"\s*[:=]\s*[\"']?(?P<value>[^\n`<>]{8,}?)\s*$"
        ),
    ),
    (
        "labeled_secret",
        re.compile(
            r"(?im)^\s*(?:[-*]\s+)?(?:API\s+(?:token|key)|Access\s+token)"
            r"\s*[:=]\s*[\"']?(?P<value>[^\n`<>]{8,}?)\s*$"
        ),
    ),
    ("credentialed_url", re.compile(r"\b(?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s/:]+:[^@\s]+@[^\s]+")),
    (
        "url_token_parameter",
        re.compile(
            r"(?i)\bhttps?://[^\s#]*[?&](?:access_token|api_key|token)="
            r"(?P<value>[^&#\s]{8,})"
        ),
    ),
    ("authorization_bearer", re.compile(r"(?i)\bAuthorization\s*[:=]\s*Bearer\s+(?P<value>[^\s`\"'<>]+)")),
]
SAFE_REFERENCE = re.compile(r"(?ix)^(?:\$+\{?[A-Z][A-Z0-9_]*\}?|\[?REDACTED\]?|<REDACTED>|(?:stored[-_ ]in[-_ ])?(?:keychain|secret[-_ ]manager|1password|vault)|configured[-_ ]externally|not[-_ ]set|unset)$")
STATE_CODES = {"workspace_missing", "workspace_not_directory", "git_state_unavailable", "missing_snapshot_field", "invalid_snapshot_paths", "invalid_working_tree_state", "workspace_drift", "branch_drift", "head_drift", "snapshot_branch_drift", "snapshot_head_drift", "working_tree_drift", "staged_drift", "unstaged_drift", "untracked_drift"}


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    line: int | None = None


class GitStateReadError(RuntimeError):
    """Raised when Git state cannot be read safely."""


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    metadata = {}
    for raw in text[4:end].splitlines():
        if ":" in raw and not raw.lstrip().startswith("#"):
            key, value = raw.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")
    return metadata, text[end + 5 :]


def split_sections(body: str) -> dict[str, str]:
    sections, current, lines = {}, None, []
    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current, lines = match.group(1).strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def parse_snapshot_fields(body: str) -> dict[str, str]:
    snapshot, fields = split_sections(body).get("Workspace Snapshot", ""), {}
    for field in SNAPSHOT_FIELDS:
        match = re.search(rf"^-\s+{re.escape(field)}:\s+(.+?)\s*$", snapshot, re.MULTILINE)
        if match:
            fields[field] = match.group(1).strip().strip("`")
    return fields


def parse_path_set(value: str) -> set[str]:
    if not value or value.casefold() == "none":
        return set()
    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("path list must be a JSON array of strings")
        return set(parsed)
    return {value.strip("`")}


def check_structure(text: str, metadata: dict[str, str], body: str) -> list[Finding]:
    findings: list[Finding] = []
    if not metadata:
        findings.append(Finding("high", "missing_frontmatter", "Missing or malformed YAML frontmatter."))
    else:
        for key in REQUIRED_FRONTMATTER:
            if not metadata.get(key):
                findings.append(Finding("high", "missing_metadata", f"Missing frontmatter field: {key}."))

    sections = split_sections(body)
    for section in REQUIRED_SECTIONS:
        content = sections.get(section)
        if content is None:
            findings.append(Finding("high", "missing_section", f"Missing section: ## {section}."))
        elif not content:
            findings.append(Finding("high", "empty_section", f"Section is empty: ## {section}."))

    if "### Done When" not in sections.get("Mission", ""):
        findings.append(Finding("high", "missing_done_when", "Mission must include a '### Done When' subsection."))
    if not re.search(r"^\s*\d+\.\s+\[ \]\s+\S", sections.get("Work Remaining", ""), re.MULTILINE):
        findings.append(Finding("high", "no_unfinished_task", "Work Remaining must contain an unchecked numbered task."))

    # These markers come from the distributed template and should never survive into a handoff.
    placeholder = re.compile(r"\[(?:TODO|ISO-8601|absolute |branch name|full commit|short kebab|Concise Task|The outcome|Observable |Required |Included |Explicitly |Decision |Applicable |Assumption |Completed |What is |Work not |First executable|Second task|Later task|Write one concrete|relative or absolute|Role in |Modified /|Plan, design|Non-obvious|Exact command|Failure and |Command or check|Why it remains|Paths or None|Relevant process|Required environment|Blocker, owner|Question asked)", re.IGNORECASE)
    for match in placeholder.finditer(text):
        findings.append(Finding("high", "placeholder", f"Unresolved template placeholder: {match.group(0)}", line_number(text, match.start())))
    return findings


def check_secrets(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for name, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            value = groups.get("value") if groups else None
            if (
                name == "secret_assignment"
                and groups.get("name", "").casefold() == "authorization"
                and (value or "").casefold().startswith("bearer ")
            ):
                continue
            if value and SAFE_REFERENCE.fullmatch(value.strip().strip("\"'")):
                continue
            findings.append(Finding("high", f"sensitive_{name}", f"Potential credential detected ({name}); redact the value or reference its storage mechanism.", line_number(text, match.start())))
    return findings


def run_git(workspace: Path, *args: str) -> tuple[int, str, str]:
    try:
        result = subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return 1, "", str(error)
    return result.returncode, result.stdout.rstrip("\n"), result.stderr.rstrip("\n")


def git_snapshot(workspace: Path) -> dict[str, object] | None:
    code, root, error = run_git(workspace, "rev-parse", "--show-toplevel")
    if code != 0:
        if "not a git repository" in error.casefold() and not any((parent / ".git").exists() for parent in (workspace, *workspace.parents)):
            return None
        raise GitStateReadError(error or "git rev-parse failed")
    code, branch, error = run_git(workspace, "branch", "--show-current")
    if code != 0:
        raise GitStateReadError(error or "git branch failed")
    code, head, error = run_git(workspace, "rev-parse", "HEAD")
    if code != 0:
        raise GitStateReadError(error or "git rev-parse HEAD failed")
    state: dict[str, set[str]] = {}
    commands = {
        "staged": ("diff", "--cached", "--name-only", "--no-renames", "-z"),
        "unstaged": ("diff", "--name-only", "--no-renames", "-z"),
        "untracked": ("ls-files", "--others", "--exclude-standard", "-z"),
    }
    for name, command in commands.items():
        code, output, error = run_git(workspace, *command)
        if code != 0:
            raise GitStateReadError(error or f"git {command[0]} failed")
        state[name] = {path for path in output.split("\0") if path}
    return {
        "workspace": str(Path(root).resolve()),
        "branch": branch or "detached",
        "head": head,
        "dirty": any(state.values()),
        **state,
    }


def check_state(metadata: dict[str, str], body: str) -> list[Finding]:
    workspace_value = metadata.get("workspace", "")
    if not workspace_value:
        return []
    workspace = Path(workspace_value).expanduser()
    if not workspace.exists():
        return [Finding("high", "workspace_missing", f"Recorded workspace does not exist: {workspace}.")]
    if not workspace.is_dir():
        return [Finding("high", "workspace_not_directory", f"Recorded workspace is not a directory: {workspace}.")]
    try:
        current = git_snapshot(workspace)
    except GitStateReadError as error:
        return [Finding("high", "git_state_unavailable", f"Unable to read current Git state: {error}.")]

    recorded = parse_snapshot_fields(body)
    findings: list[Finding] = []
    for field in SNAPSHOT_FIELDS:
        if field not in recorded:
            findings.append(Finding("high", "missing_snapshot_field", f"Workspace Snapshot is missing field: {field}."))

    paths: dict[str, set[str]] = {}
    for field in ("Staged", "Unstaged", "Untracked"):
        if field not in recorded:
            continue
        try:
            paths[field] = parse_path_set(recorded[field])
        except (ValueError, json.JSONDecodeError) as error:
            findings.append(Finding("high", "invalid_snapshot_paths", f"{field} must be None or a JSON array: {error}."))

    working_tree = recorded.get("Working tree", "").casefold()
    if working_tree not in {"clean", "dirty", "not-a-git-repository"}:
        findings.append(Finding("high", "invalid_working_tree_state", "Working tree must be clean, dirty, or not-a-git-repository."))

    if current is None:
        snapshot_workspace = recorded.get("Workspace")
        if snapshot_workspace and Path(snapshot_workspace).expanduser().resolve() != workspace.resolve():
            findings.append(Finding("medium", "workspace_drift", "Workspace Snapshot path differs from the recorded workspace."))
        if metadata.get("branch") != "not-a-git-repository" or metadata.get("head") != "not-a-git-repository":
            findings.append(Finding("medium", "branch_drift", "Recorded Git metadata but workspace is not a Git repository."))
        if working_tree not in {"clean", "not-a-git-repository"}:
            findings.append(Finding("medium", "working_tree_drift", "Non-Git workspace must record Working tree as clean or not-a-git-repository."))
        for field in ("Branch", "HEAD"):
            if recorded.get(field) not in {None, "not-a-git-repository"}:
                findings.append(Finding("medium", "workspace_drift", f"Non-Git workspace must record {field} as not-a-git-repository."))
        for field, code in (
            ("Staged", "staged_drift"),
            ("Unstaged", "unstaged_drift"),
            ("Untracked", "untracked_drift"),
        ):
            if paths.get(field):
                findings.append(Finding("medium", code, f"Non-Git workspace must record {field} as None."))
        return findings

    git_root = Path(str(current["workspace"]))
    if workspace.resolve() != git_root:
        findings.append(Finding("medium", "workspace_drift", "Recorded workspace is not the current Git root."))
    snapshot_workspace = recorded.get("Workspace")
    if snapshot_workspace and Path(snapshot_workspace).expanduser().resolve() != git_root:
        findings.append(Finding("medium", "workspace_drift", "Workspace Snapshot path differs from the current Git root."))

    for field, current_value, code in (("branch", current["branch"], "branch_drift"), ("head", current["head"], "head_drift")):
        if metadata.get(field) and metadata[field] != current_value:
            findings.append(Finding("medium", code, f"{field} changed: recorded '{metadata[field]}', current '{current_value}'."))
    for field, current_value, code in (
        ("Branch", current["branch"], "snapshot_branch_drift"),
        ("HEAD", current["head"], "snapshot_head_drift"),
    ):
        if recorded.get(field) and recorded[field] != current_value:
            findings.append(Finding("medium", code, f"Workspace Snapshot {field} differs from the current Git state."))

    if working_tree not in {"clean", "dirty"}:
        findings.append(Finding("high", "invalid_working_tree_state", "Git workspace must record Working tree as clean or dirty."))
    elif (working_tree == "dirty") != bool(current["dirty"]):
        findings.append(Finding("medium", "working_tree_drift", "Working tree clean/dirty state changed."))
    for field, key, code in (("Staged", "staged", "staged_drift"), ("Unstaged", "unstaged", "unstaged_drift"), ("Untracked", "untracked", "untracked_drift")):
        if field in paths and paths[field] != current[key]:
            findings.append(Finding("medium", code, f"{field} paths changed."))
    return findings


def validate(path: Path, should_check_state: bool) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    findings = check_structure(text, metadata, body)
    findings.extend(check_secrets(text))
    structure_valid = not any(item.severity == "high" for item in findings)
    if should_check_state:
        findings.extend(check_state(metadata, body))
    counts = {severity: sum(item.severity == severity for item in findings) for severity in ("high", "medium", "low")}
    state_compatible = not any(item.code in STATE_CODES for item in findings)
    return {
        "file": str(path),
        "valid": structure_valid and (not should_check_state or state_compatible),
        "structure_valid": structure_valid,
        "state_compatible": state_compatible if should_check_state else None,
        "state_checked": should_check_state,
        "metadata": metadata,
        "counts": counts,
        "findings": [asdict(item) for item in findings],
    }


def print_human(report: dict[str, object]) -> None:
    counts = report["counts"]
    print(f"{'PASS' if report['valid'] else 'FAIL'}: {report['file']}")
    print(f"Findings: high={counts['high']} medium={counts['medium']} low={counts['low']}")
    for finding in report["findings"]:
        location = f" line {finding['line']}" if finding["line"] else ""
        print(f"- [{finding['severity']}] {finding['code']}{location}: {finding['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path, help="Handoff Markdown file to validate.")
    parser.add_argument("--check-state", action="store_true", help="Compare recorded workspace state with the current workspace.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args()
    if not args.handoff.is_file():
        print(f"Handoff file not found: {args.handoff}", file=sys.stderr)
        return 2
    try:
        report = validate(args.handoff, args.check_state)
    except (OSError, UnicodeError) as error:
        print(f"Unable to read handoff: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
