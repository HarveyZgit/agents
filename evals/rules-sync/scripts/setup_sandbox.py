#!/usr/bin/env python3
"""Create isolated fake-home sandboxes for rules-sync behavior evals.

Host layout is read from the adapter's own host table instead of being restated
here, so this script stays host-neutral and cannot drift from the Skill it tests.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


EVAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_ROOT.parents[1]
ADAPTER_PATH = REPO_ROOT / "skills" / "rules-sync" / "scripts" / "sync_rules.py"
MARKER_NAME = ".rules-sync-eval"
MARKER_TEXT = "managed by rules-sync evals\n"
PREEXISTING_MARKDOWN = "# Global notes\n\n- Keep answers short.\n"
PREEXISTING_CONFIG = {"theme": "dark"}
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


def load_adapter():
    spec = importlib.util.spec_from_file_location("rules_sync_adapter", ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registering before exec keeps dataclass field resolution working on 3.9.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    """Refuse anything that could make a sandbox overwrite a real home directory."""
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
        raise ValueError(
            f"Target already exists; pass --replace only for a managed eval directory: {target}"
        )
    if not marker.is_file() or marker.read_text(encoding="utf-8") != MARKER_TEXT:
        raise ValueError(f"Refusing to replace directory without the eval marker: {target}")
    shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)


def seed_hosts(adapter) -> None:
    """Give every host a plausible pre-existing config so clobbering is detectable."""
    for host in adapter.HOSTS:
        adapter.host_path(host.detect).mkdir(parents=True, exist_ok=True)
        if not host.target:
            continue
        target = adapter.host_path(host.target)
        if host.mode == "inline":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(PREEXISTING_MARKDOWN, encoding="utf-8")
        elif host.mode == "config":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(PREEXISTING_CONFIG, indent=2) + "\n", encoding="utf-8"
            )


def install(adapter) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        exit_code = adapter.main(["install"])
    if exit_code != 0:
        raise RuntimeError("adapter install failed while preparing the sandbox")


def introduce_drift(adapter) -> list[str]:
    """Break one live reference and one generated block, the two realistic failures."""
    notes = []
    for host in adapter.HOSTS:
        if host.mode == "link":
            links = sorted(adapter.host_path(host.target).glob("*.md"))
            if links:
                links[0].unlink()
                notes.append(f"removed {links[0]}")
        elif host.mode == "inline":
            target = adapter.host_path(host.target)
            content = target.read_text(encoding="utf-8")
            marker_end = content.find(adapter.END_MARKER)
            if marker_end != -1:
                target.write_text(
                    content[:marker_end] + "- hand-edited stale line\n" + content[marker_end:],
                    encoding="utf-8",
                )
                notes.append(f"edited the managed block in {target}")
    return notes


def build(target: Path, scenario: str) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    (target / MARKER_NAME).write_text(MARKER_TEXT, encoding="utf-8")
    os.environ["HOME"] = str(target)
    os.environ.pop("AGENT_RULES_HOME", None)
    adapter = load_adapter()
    seed_hosts(adapter)
    if scenario == "fresh":
        return []
    install(adapter)
    if scenario == "drifted":
        return introduce_drift(adapter)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("fresh", "installed", "drifted"))
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

    notes = build(target, args.scenario)
    print(target)
    for note in notes:
        print(f"# {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
