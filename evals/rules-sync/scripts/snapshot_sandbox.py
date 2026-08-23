#!/usr/bin/env python3
"""Print a deterministic snapshot of an eval sandbox for grading.

Runs after a scenario so every configuration produces a comparable artifact:
what exists, which links point where, and the full text of the files a host
actually reads. Host locations come from the adapter's table, not from here.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_ROOT.parents[1]
ADAPTER_PATH = REPO_ROOT / "skills" / "rules-sync" / "scripts" / "sync_rules.py"
SKIPPED_TOP_LEVEL = {"Library"}


def load_adapter():
    spec = importlib.util.spec_from_file_location("rules_sync_adapter", ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def describe_tree(sandbox: Path) -> list[str]:
    lines = []
    for path in sorted(sandbox.rglob("*")):
        relative = path.relative_to(sandbox)
        if relative.parts and relative.parts[0] in SKIPPED_TOP_LEVEL:
            continue
        if path.is_symlink():
            lines.append(f"symlink {relative} -> {os.readlink(path)}")
        elif path.is_dir():
            lines.append(f"dir     {relative}")
        else:
            lines.append(f"file    {relative}")
    return lines


def describe_file(path: Path, sandbox: Path) -> list[str]:
    label = path.relative_to(sandbox) if path.is_relative_to(sandbox) else path
    if not path.exists():
        return [f"--- {label}: absent", ""]
    if path.is_dir():
        entries = sorted(item.name for item in path.iterdir())
        return [f"--- {label}: directory with {', '.join(entries) or 'no entries'}", ""]
    return [f"--- {label}", path.read_text(encoding="utf-8").rstrip("\n"), ""]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sandbox", type=Path)
    args = parser.parse_args()

    sandbox = args.sandbox.expanduser().resolve()
    if not sandbox.is_dir():
        parser.error(f"not a directory: {sandbox}")

    os.environ["HOME"] = str(sandbox)
    os.environ.pop("AGENT_RULES_HOME", None)
    adapter = load_adapter()

    print(f"# sandbox {sandbox}")
    print("\n## tree")
    print("\n".join(describe_tree(sandbox)))

    print("\n## host files")
    for host in adapter.HOSTS:
        if not host.target:
            continue
        for line in describe_file(adapter.host_path(host.target), sandbox):
            print(line)

    print("## store")
    for line in describe_file(adapter.receipt_path(), sandbox):
        print(line)
    for fragment in sorted(adapter.store_dir().glob("*.md")):
        print(f"--- {fragment.relative_to(sandbox)}: {len(fragment.read_bytes())} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
