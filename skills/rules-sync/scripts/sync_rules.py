#!/usr/bin/env python3
"""Install, verify, and remove shared rule fragments in agent host configurations.

This file is the host adapter. It is the one place in the repository allowed to
name concrete agent hosts and their runtime paths: every other reusable asset
stays host-neutral, and this script absorbs the coupling so the Skill body does
not have to. Host knowledge lives in HOSTS below; everything else is generic.

Wiring prefers a live reference (symlink, import, config glob) so a later
revision of the fragments reaches the host without rewriting its config. Only
hosts with no reference mechanism receive inlined text.
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# The tracked branch: `install` and `update` fetch its current tip, so publishing
# fragments needs no change here. Pass --ref to pin a specific revision instead.
# The receipt records the commit each install resolved to, so `check` can tell
# whether the branch has moved since.
SOURCE_REPO = "HarveyZgit/agents"
SOURCE_REF = "main"
SOURCE_SUBDIR = "rules"

BEGIN_MARKER = "<!-- BEGIN agents-rules (managed by rules-sync) -->"
END_MARKER = "<!-- END agents-rules -->"
RECEIPT_NAME = ".receipt.json"
MANUAL_DIRNAME = ".out"
RECEIPT_VERSION = 1


@dataclass(frozen=True)
class Host:
    """A host's global-rules mechanism.

    mode is how fragments reach the host:
      link    symlink each fragment into a directory the host loads on its own
      import  managed block of import directives the host expands at startup
      inline  managed block of fragment bodies, for hosts that expand nothing
      config  register a glob in the host's config file
      mdc     write one .mdc file per fragment into a directory the host loads,
              with host-specific frontmatter (alwaysApply: true)
      manual  render text the user pastes into a UI field the host owns
    """

    key: str
    label: str
    mode: str
    detect: str
    target: str
    # A second spelling the host reads instead of target, when it accepts one.
    # Writing target while this exists would leave two configs whose precedence
    # the host does not document.
    alt_target: str = ""
    note: str = ""


HOSTS: tuple[Host, ...] = (
    Host(
        key="claude-code",
        label="Claude Code",
        mode="link",
        detect="~/.claude",
        target="~/.claude/rules",
        note="User-level rules load in every project; the directory resolves symlinks.",
    ),
    Host(
        key="codex",
        label="Codex",
        mode="inline",
        detect="~/.codex",
        target="~/.codex/AGENTS.md",
        note="Import directives are not expanded here, so bodies are inlined.",
    ),
    Host(
        key="cursor",
        label="Cursor CLI",
        mode="mdc",
        detect="~/.cursor",
        target="~/.cursor/rules",
        note="User-level .mdc files load for the CLI agent; alwaysApply is set so core fragments apply in every session.",
    ),
    Host(
        key="grok",
        label="Grok",
        mode="link",
        detect="~/.grok",
        target="~/.grok/rules",
        note="Home rules load in every project; the directory resolves symlinks.",
    ),
    Host(
        key="gemini-cli",
        label="Gemini CLI",
        mode="import",
        detect="~/.gemini",
        target="~/.gemini/GEMINI.md",
        note="Absolute import paths are expanded into context at startup.",
    ),
    Host(
        key="opencode",
        label="OpenCode",
        mode="config",
        detect="~/.config/opencode",
        target="~/.config/opencode/opencode.json",
        alt_target="~/.config/opencode/opencode.jsonc",
        note="A project-level config that also sets instructions replaces this array instead of merging.",
    ),
)

HOSTS_BY_KEY = {host.key: host for host in HOSTS}


@dataclass
class Fragment:
    name: str
    filename: str
    description: str
    tier: str
    body: str


@dataclass
class Action:
    """One planned filesystem change, with a preview for --dry-run.

    conflict marks a plan that cannot be applied: install refuses before writing
    anything, while check reports it as drift instead of aborting the run.
    retires names a path the receipt should forget once this action applies.
    """

    summary: str
    path: Path
    diff: str = ""
    apply: object = None
    artifact: dict = field(default_factory=dict)
    conflict: str = ""
    retires: str = ""


def store_dir() -> Path:
    override = os.environ.get("AGENT_RULES_HOME")
    base = Path(override) if override else Path.home() / ".agents" / "rules"
    return base.expanduser()


def receipt_path() -> Path:
    return store_dir() / RECEIPT_NAME


def manual_dir() -> Path:
    return store_dir() / MANUAL_DIRNAME


def host_path(raw: str) -> Path:
    return Path(raw).expanduser()


def read_receipt() -> dict:
    path = receipt_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        # Treating an unreadable receipt as "nothing installed" would strand
        # every wired host, so stop and let the user decide.
        raise SystemExit(f"cannot read {path} ({error}); repair or delete it before continuing")
    broken = f"{path} is malformed; repair or delete it before continuing"
    if not isinstance(data, dict):
        raise SystemExit(broken)
    hosts = data.get("hosts", {})
    if not isinstance(hosts, dict):
        raise SystemExit(broken)
    for record in hosts.values():
        artifacts = record.get("artifacts", []) if isinstance(record, dict) else None
        if not isinstance(artifacts, list) or any(
            not isinstance(item, dict) or not item.get("path") for item in artifacts
        ):
            raise SystemExit(broken)
    return data


def write_receipt(data: dict) -> None:
    write_file(receipt_path(), json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def parse_fragment(filename: str, text: str) -> Fragment | None:
    """Return a fragment, or None when the file is not a distributable fragment.

    Frontmatter is selection metadata: it is stripped before the body reaches a
    host, and its absence means the file is documentation rather than a rule.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        return None
    head = text[4 : end + 1]
    body = text[end + 5 :].strip()
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip("\"'")
    if not meta.get("name") or not meta.get("tier") or not body:
        return None
    return Fragment(
        name=meta["name"],
        filename=filename,
        description=meta.get("description", ""),
        tier=meta["tier"],
        body=body,
    )


def download(url: str, attempts: int = 3) -> bytes:
    """Read a URL, retrying transient transport failures.

    A dropped TLS connection is common enough here to fail an otherwise fine
    unattended install, and the request is idempotent, so retrying is free.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "rules-sync"})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, OSError) as error:
            last_error = error
            if isinstance(error, urllib.error.HTTPError) and error.code < 500:
                break
            time.sleep(2**attempt)
    raise SystemExit(f"cannot download {url}: {last_error}")


def resolve_commit(ref: str) -> str | None:
    """The commit a ref points at now, or None when the remote cannot be asked.

    Reads git's ref advertisement rather than the REST API: it needs no token and
    has no hourly budget, which a handful of checks would otherwise exhaust.

    Non-fatal by design: this only sharpens reporting, so a machine that is
    offline still installs and still gets a drift report for its wiring.
    """
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref
    request = urllib.request.Request(
        f"https://github.com/{SOURCE_REPO}.git/info/refs?service=git-upload-pack",
        headers={"User-Agent": "rules-sync"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            advertisement = response.read()
    except (urllib.error.URLError, OSError):
        return None
    for kind in (b"heads", b"tags"):
        pattern = rb"([0-9a-f]{40}) refs/" + kind + b"/" + re.escape(ref.encode()) + rb"[\x00\n]"
        match = re.search(pattern, advertisement)
        if match:
            return match.group(1).decode("ascii")
    return None


def fetch_fragments(ref: str) -> list[Fragment]:
    """Download the requested revision and return its core fragments."""
    payload = download(f"https://codeload.github.com/{SOURCE_REPO}/tar.gz/{ref}")

    wanted = re.compile(rf"^[^/]+/{re.escape(SOURCE_SUBDIR)}/([^/]+\.md)$")
    fragments: list[Fragment] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                match = wanted.match(member.name)
                if not member.isfile() or not match:
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                fragment = parse_fragment(match.group(1), handle.read().decode("utf-8"))
                if fragment and fragment.tier == "core":
                    fragments.append(fragment)
    except (tarfile.TarError, UnicodeDecodeError) as error:
        raise SystemExit(f"cannot read the archive for {SOURCE_REPO}@{ref}: {error}")
    if not fragments:
        raise SystemExit(f"no core fragments found in {SOURCE_REPO}@{ref}/{SOURCE_SUBDIR}")
    return sorted(fragments, key=lambda item: item.name)


def read_store_fragments() -> list[Fragment]:
    """Fragments already materialized locally, so check and uninstall stay offline.

    Stored files hold the body only: hosts that load them directly should not see
    selection metadata, so the store trades self-description for clean artifacts
    and the receipt keeps the inventory.
    """
    fragments = []
    for path in sorted(store_dir().glob("*.md")):
        body = path.read_text(encoding="utf-8").strip()
        if body:
            fragments.append(
                Fragment(
                    name=path.stem,
                    filename=path.name,
                    description="",
                    tier="core",
                    body=body,
                )
            )
    return sorted(fragments, key=lambda item: item.name)


def detected(host: Host) -> bool:
    return host_path(host.detect).exists()


def resolve_hosts(requested: list[str] | None, receipt: dict) -> list[Host]:
    if requested:
        unknown = [key for key in requested if key not in HOSTS_BY_KEY]
        if unknown:
            known = ", ".join(HOSTS_BY_KEY)
            raise SystemExit(f"unknown host(s): {', '.join(unknown)}. Known hosts: {known}")
        return [HOSTS_BY_KEY[key] for key in requested]
    recorded = [HOSTS_BY_KEY[key] for key in receipt.get("hosts", {}) if key in HOSTS_BY_KEY]
    if recorded:
        return recorded
    return [host for host in HOSTS if detected(host)]


def diff_text(path: Path, old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(lines)


def render_block(host: Host, fragments: list[Fragment], ref: str) -> str:
    provenance = (
        f"<!-- {SOURCE_REPO}@{ref[:12]} · regenerate with rules-sync; "
        "edits inside this block are overwritten -->"
    )
    if host.mode == "import":
        payload = "\n".join(f"@{store_dir() / fragment.filename}" for fragment in fragments)
    else:
        payload = "\n\n".join(fragment.body for fragment in fragments)
    return f"{BEGIN_MARKER}\n{provenance}\n\n{payload}\n{END_MARKER}"


def find_block(current: str) -> tuple[int, int] | None:
    """Locate the managed block, or None when the file has none.

    The end marker is searched from the begin marker onward: the marker text can
    legitimately appear earlier in the user's prose, and matching that copy would
    make every run append another block.
    """
    start = current.find(BEGIN_MARKER)
    if start == -1:
        return None
    end = current.find(END_MARKER, start)
    if end == -1:
        return None
    return start, end + len(END_MARKER)


def replace_block(current: str, block: str) -> str:
    span = find_block(current)
    if span:
        start, end = span
        return current[:start] + block + current[end:]
    if not current.strip():
        return block + "\n"
    return current.rstrip("\n") + "\n\n" + block + "\n"


def strip_block(current: str) -> str:
    span = find_block(current)
    if not span:
        return current
    start, end = span
    head = current[:start].rstrip("\n")
    tail = current[end:].lstrip("\n")
    remainder = f"{head}\n{tail}" if head else tail
    return "" if not remainder.strip() else remainder


def foreign_copies(current: str, fragments: list[Fragment]) -> list[str]:
    """Fragment titles already present in the file outside our managed block.

    Another tool may publish the same fragments under its own markers. Appending
    our block as well would load the same rules into the host twice, so this is a
    conflict to resolve rather than an update to apply.
    """
    span = find_block(current)
    outside = current[: span[0]] + current[span[1] :] if span else current
    titles = []
    for fragment in fragments:
        title = fragment.body.splitlines()[0].strip()
        if title and title in outside:
            titles.append(title)
    return titles


def write_file(path: Path, content: str) -> None:
    # Write through a symlink so a host config kept in a dotfile repository stays
    # linked instead of being replaced by a regular file.
    if path.is_symlink():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Carry the destination's permission bits onto the replacement: a config the
    # user restricted must not come back with default permissions.
    mode = path.stat().st_mode & 0o7777 if path.exists() else None
    temporary = path.with_name(path.name + ".rules-sync.tmp")
    temporary.write_text(content, encoding="utf-8")
    if mode is not None:
        temporary.chmod(mode)
    temporary.replace(path)


def plan_store(fragments: list[Fragment], receipt: dict) -> list[Action]:
    actions: list[Action] = []
    store = store_dir()
    wanted = {fragment.filename for fragment in fragments}
    for fragment in fragments:
        path = store / fragment.filename
        content = fragment.body + "\n"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        if old == content:
            continue
        verb = "update" if old else "write"
        actions.append(
            Action(
                summary=f"{verb} fragment {fragment.name}",
                path=path,
                diff=diff_text(path, old, content),
                apply=lambda path=path, content=content: write_file(path, content),
            )
        )
    for stale in sorted(set(receipt.get("fragments", [])) - wanted):
        path = store / stale
        if path.exists():
            actions.append(
                Action(
                    summary=f"remove withdrawn fragment {stale}",
                    path=path,
                    apply=lambda path=path: path.unlink(),
                )
            )
    return actions


def plan_link(host: Host, fragments: list[Fragment]) -> list[Action]:
    actions: list[Action] = []
    target_dir = host_path(host.target)
    store = store_dir()
    if target_dir.exists() and not target_dir.is_dir():
        return [
            Action(
                summary=f"{target_dir} is not a directory",
                path=target_dir,
                conflict=f"{target_dir} is not a directory; move it aside",
            )
        ]
    wanted = {fragment.filename for fragment in fragments}
    for fragment in fragments:
        link = target_dir / fragment.filename
        source = store / fragment.filename
        artifact = {"path": str(link), "kind": "symlink"}
        if link.is_symlink() and Path(os.readlink(link)) == source:
            actions.append(
                Action(summary=f"{link} already linked", path=link, artifact=artifact)
            )
            continue
        if link.exists() and not link.is_symlink():
            actions.append(
                Action(
                    summary=f"{link} exists and is not a symlink",
                    path=link,
                    conflict=f"{link} exists and is not a symlink; move it aside",
                )
            )
            continue
        # A link to a different source means an earlier setup owns this name, so
        # name the old target in the plan instead of silently taking it over.
        existing_target = os.readlink(link) if link.is_symlink() else None

        def apply(link=link, source=source) -> None:
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(source)

        summary = (
            f"relink {fragment.name} in {target_dir} (currently -> {existing_target})"
            if existing_target
            else f"link {fragment.name} into {target_dir}"
        )
        actions.append(Action(summary=summary, path=link, apply=apply, artifact=artifact))

    # A fragment withdrawn upstream leaves a symlink that now dangles. Only links
    # pointing into our own store are ours to remove.
    if target_dir.is_dir():
        for entry in sorted(target_dir.iterdir()):
            if entry.name in wanted or not entry.is_symlink():
                continue
            if Path(os.readlink(entry)).parent != store:
                continue
            actions.append(
                Action(
                    summary=f"unlink withdrawn {entry.name} from {target_dir}",
                    path=entry,
                    apply=lambda entry=entry: entry.unlink(),
                    retires=str(entry),
                )
            )
    return actions


def plan_block(host: Host, fragments: list[Fragment], ref: str) -> list[Action]:
    path = host_path(host.target)
    existed = path.exists()
    old = path.read_text(encoding="utf-8") if existed else ""
    duplicates = foreign_copies(old, fragments)
    if duplicates:
        return [
            Action(
                summary=f"{path} already carries these fragments outside our block",
                path=path,
                conflict=(
                    f"{path} already contains {len(duplicates)} of these fragments "
                    f"outside our managed block (first: {duplicates[0]}); remove that "
                    "copy so the rules are not loaded twice"
                ),
            )
        ]
    new = replace_block(old, render_block(host, fragments, ref))
    artifact = {"path": str(path), "kind": "block", "created": not existed}
    if old == new:
        return [Action(summary=f"{path} already current", path=path, artifact=artifact)]
    return [
        Action(
            summary=f"{'update' if existed else 'create'} managed block in {path}",
            path=path,
            diff=diff_text(path, old, new),
            apply=lambda: write_file(path, new),
            artifact=artifact,
        )
    ]


def config_glob() -> str:
    return str(store_dir() / "*.md")


def plan_config(host: Host) -> list[Action]:
    path = host_path(host.target)
    alternate = host_path(host.alt_target) if host.alt_target else None
    if alternate and alternate.exists():
        if path.exists():
            return [
                Action(
                    summary=f"{path} and {alternate} both exist",
                    path=path,
                    conflict=(
                        f"{path} and {alternate} both exist; the host does not "
                        "document which wins. Keep one and rerun"
                    ),
                )
            ]
        # Comments make this file unparseable as JSON, and rewriting it from a
        # stripped parse would drop them, so registration stays manual here.
        registered = config_glob() in alternate.read_text(encoding="utf-8")
        if registered:
            return [Action(summary=f"{alternate} already registers the glob", path=alternate)]
        return [
            Action(
                summary=f"{alternate} needs the glob added by hand",
                path=alternate,
                conflict=(
                    f'{alternate} is JSONC and cannot be edited safely; add '
                    f'"{config_glob()}" to its instructions array yourself'
                ),
            )
        ]

    existed = path.exists()
    old = path.read_text(encoding="utf-8") if existed else ""
    try:
        config = json.loads(old) if old.strip() else {}
    except json.JSONDecodeError as error:
        raise SystemExit(f"{path} is not valid JSON ({error}); fix it before installing")
    if not isinstance(config, dict):
        raise SystemExit(f"{path} must contain a JSON object")

    existing = config.get("instructions", [])
    if not isinstance(existing, list):
        raise SystemExit(
            f"{path} has a non-list `instructions` value; fix it before installing"
        )
    instructions = list(existing)
    artifact = {"path": str(path), "kind": "config", "created": not existed}
    if config_glob() in instructions:
        return [Action(summary=f"{path} already current", path=path, artifact=artifact)]
    instructions.append(config_glob())
    config["instructions"] = instructions
    new = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    return [
        Action(
            summary=f"register rules glob in {path}",
            path=path,
            diff=diff_text(path, old, new),
            apply=lambda: write_file(path, new),
            artifact=artifact,
        )
    ]


def render_mdc(fragment: Fragment) -> str:
    """One host-owned rule file: our body plus the frontmatter this host requires.

    The store keeps fragments host-neutral. This host ignores a plain .md, and
    only loads a file that declares alwaysApply, so the adapter wraps the body
    here rather than leaking that spelling into the fragment.
    """
    return (
        f"---\n"
        f"description: {fragment.description}\n"
        f"alwaysApply: true\n"
        f"---\n\n"
        f"{fragment.body}\n"
    )


def managed_mdc(text: str) -> bool:
    """True when the file is in the shape we write, not a user's own rule.

    A same-named file the user authored may also be YAML, so we require the
    opening we generate (description + alwaysApply: true) before treating it
    as ours to update or remove.
    """
    if not text.startswith("---\ndescription:"):
        return False
    end = text.find("\n---\n", 3)
    if end == -1:
        return False
    head = text[4 : end + 1]
    return any(line.strip() == "alwaysApply: true" for line in head.splitlines())


def mdc_description(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("description:"):
            return line.partition(":")[2].strip()
    return ""


def plan_mdc(
    host: Host, fragments: list[Fragment], previous_names: set[str] | None = None
) -> list[Action]:
    actions: list[Action] = []
    target_dir = host_path(host.target)
    if target_dir.exists() and not target_dir.is_dir():
        return [
            Action(
                summary=f"{target_dir} is not a directory",
                path=target_dir,
                conflict=f"{target_dir} is not a directory; move it aside",
            )
        ]
    wanted = {fragment.name for fragment in fragments}
    for fragment in fragments:
        path = target_dir / f"{fragment.name}.mdc"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        desired = render_mdc(fragment)
        if not fragment.description and old and managed_mdc(old):
            # check reads the store, which has no description. Reusing the one
            # already on disk keeps a description-only rewrite from looking
            # like drift after a successful install.
            desired = render_mdc(
                Fragment(
                    name=fragment.name,
                    filename=fragment.filename,
                    description=mdc_description(old),
                    tier=fragment.tier,
                    body=fragment.body,
                )
            )
        artifact = {"path": str(path), "kind": "file", "created": not path.exists()}
        if old == desired and path.exists() and not path.is_symlink():
            actions.append(
                Action(summary=f"{path} already current", path=path, artifact=artifact)
            )
            continue
        if path.exists() and not managed_mdc(old):
            actions.append(
                Action(
                    summary=f"{path} exists and is not a managed .mdc file",
                    path=path,
                    conflict=f"{path} exists and is not a managed .mdc file; move it aside",
                )
            )
            continue

        def apply(path=path, desired=desired) -> None:
            write_file(path, desired)

        verb = "update" if path.exists() else "write"
        actions.append(
            Action(
                summary=f"{verb} {fragment.name}.mdc in {target_dir}",
                path=path,
                diff=diff_text(path, old, desired),
                apply=apply,
                artifact=artifact,
            )
        )

    # A fragment withdrawn upstream leaves a .mdc we wrote. Only names we
    # previously installed, and files that still look like ours, are ours
    # to remove; a user's own .mdc in the same directory stays.
    for name in sorted((previous_names or set()) - wanted):
        path = target_dir / f"{name}.mdc"
        if not path.is_file() or path.is_symlink():
            continue
        if not managed_mdc(path.read_text(encoding="utf-8")):
            continue
        actions.append(
            Action(
                summary=f"remove withdrawn {path.name} from {target_dir}",
                path=path,
                apply=lambda path=path: path.unlink(),
                retires=str(path),
            )
        )
    return actions


def plan_manual(host: Host, fragments: list[Fragment], ref: str) -> list[Action]:
    path = manual_dir() / f"{host.key}-user-rules.md"
    header = (
        f"<!-- {SOURCE_REPO}@{ref[:12]} · paste the text below into the host's "
        "global rules field; this file is generated -->"
    )
    content = header + "\n\n" + "\n\n".join(fragment.body for fragment in fragments) + "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    artifact = {"path": str(path), "kind": "file", "created": True}
    if old == content:
        return [Action(summary=f"{path} already current", path=path, artifact=artifact)]
    return [
        Action(
            summary=f"render paste-ready text to {path}",
            path=path,
            diff=diff_text(path, old, content),
            apply=lambda: write_file(path, content),
            artifact=artifact,
        )
    ]


def merge_artifacts(
    previous: list[dict], current: list[dict], retired: set[str] | None = None
) -> list[dict]:
    """Keep `created` sticky so a later run cannot forget that we made the file.

    Only the run that created a file may delete it on uninstall; a re-run sees the
    file already present and would otherwise downgrade the flag to False.

    Artifacts recorded earlier are carried forward unless this run retired them:
    dropping them would leave whatever they name unreverted by uninstall.
    """
    retired = retired or set()
    created_before = {item["path"] for item in previous if item.get("created")}
    merged = []
    seen = set()
    for artifact in current:
        item = dict(artifact)
        if item["path"] in created_before:
            item["created"] = True
        merged.append(item)
        seen.add(item["path"])
    for item in previous:
        if item["path"] not in seen and item["path"] not in retired:
            merged.append(dict(item))
    return merged


def plan_host(
    host: Host, fragments: list[Fragment], ref: str, receipt: dict | None = None
) -> list[Action]:
    if host.mode == "link":
        return plan_link(host, fragments)
    if host.mode in {"import", "inline"}:
        return plan_block(host, fragments, ref)
    if host.mode == "config":
        return plan_config(host)
    if host.mode == "mdc":
        previous = {Path(name).stem for name in (receipt or {}).get("fragments", [])}
        return plan_mdc(host, fragments, previous)
    return plan_manual(host, fragments, ref)


def run_actions(actions: list[Action], dry_run: bool) -> None:
    for action in actions:
        if action.apply is None:
            continue
        if dry_run:
            continue
        action.apply()


def report(actions: list[Action], dry_run: bool, show_diff: bool) -> None:
    changes = [action for action in actions if action.apply is not None]
    if not changes:
        print("  nothing to change")
        return
    for action in changes:
        print(f"  {'would ' if dry_run else ''}{action.summary}")
        if show_diff and action.diff:
            for line in action.diff.splitlines():
                print(f"    {line}")


def command_install(args: argparse.Namespace) -> int:
    receipt = read_receipt()
    ref = args.ref or SOURCE_REF
    hosts = resolve_hosts(args.host, receipt)
    if not hosts:
        print("No known host detected. Pass --host explicitly; see `list-hosts`.")
        return 1

    fragments = fetch_fragments(ref)
    source = {"repo": SOURCE_REPO, "ref": ref, "subdir": SOURCE_SUBDIR}
    commit = resolve_commit(ref)
    if commit:
        source["commit"] = commit
    stamp = f"{ref} ({commit[:12]})" if commit else ref
    print(f"source {SOURCE_REPO}@{stamp} · {len(fragments)} core fragment(s)")
    for fragment in fragments:
        print(f"  - {fragment.name}")
    if not commit:
        print(f"  note: {ref} did not resolve to a commit; `check` cannot tell whether it moves")

    # Plan every host before applying anything: a host that cannot be planned
    # must not abort the run halfway and leave earlier hosts wired with no
    # receipt to revert them.
    store_actions = plan_store(fragments, receipt)
    plans = [(host, plan_host(host, fragments, ref, receipt)) for host in hosts]
    conflicts = [action for _, actions in plans for action in actions if action.conflict]
    if conflicts:
        print("\nrefusing to write, nothing has changed. Resolve these first:")
        for action in conflicts:
            print(f"  - {action.conflict}")
        return 1

    print(f"\nstore {store_dir()}")
    report(store_actions, args.dry_run, args.diff)
    run_actions(store_actions, args.dry_run)

    host_records: dict[str, dict] = dict(receipt.get("hosts", {}))
    for host, actions in plans:
        print(f"\n{host.label} [{host.mode}] {host.note}")
        report(actions, args.dry_run, args.diff)
        run_actions(actions, args.dry_run)
        if not args.dry_run:
            host_records[host.key] = {
                "mode": host.mode,
                "artifacts": merge_artifacts(
                    receipt.get("hosts", {}).get(host.key, {}).get("artifacts", []),
                    [action.artifact for action in actions if action.artifact],
                    {action.retires for action in actions if action.retires},
                ),
            }

    # A filesystem error mid-loop deliberately leaves no receipt: the next run
    # then falls back to the hosts it detects and rewires all of them. Recording
    # a partial run instead would narrow every later run to the hosts reached
    # here, and check would call that state current.
    if not args.dry_run:
        write_receipt(
            {
                "version": RECEIPT_VERSION,
                "source": source,
                "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "fragments": [fragment.filename for fragment in fragments],
                "hosts": host_records,
            }
        )

    for host in [host for host, _ in plans if host.mode == "manual"]:
        print(
            f"\n{host.label} needs one manual step: paste "
            f"{manual_dir() / f'{host.key}-user-rules.md'} into its global rules field."
        )
    return 0


def command_check(args: argparse.Namespace) -> int:
    receipt = read_receipt()
    if not receipt:
        print("Not installed: no receipt found.")
        return 1

    installed_ref = receipt.get("source", {}).get("ref", "unknown")
    installed_commit = receipt.get("source", {}).get("commit")
    fragments = read_store_fragments()
    stamp = f"{installed_ref} ({installed_commit[:12]})" if installed_commit else installed_ref
    print(f"installed {SOURCE_REPO}@{stamp} · {len(fragments)} fragment(s)")

    wired = receipt.get("hosts", {})
    problems: list[str] = []
    if installed_ref != SOURCE_REF:
        problems.append(f"installed from {installed_ref[:12]}, not {SOURCE_REF}; run `update`")
    elif installed_commit:
        tip = resolve_commit(SOURCE_REF)
        if tip is None:
            print(f"  cannot reach the remote; whether {SOURCE_REF} moved is unknown")
        elif tip != installed_commit:
            problems.append(f"{SOURCE_REF} is now at {tip[:12]}; run `update`")
    else:
        # An install that could not reach the remote records no commit; say so
        # instead of dropping the freshness question silently.
        print(f"  no commit recorded for {installed_ref}; run `update` to record one")
    if not fragments:
        problems.append(f"{store_dir()} holds no readable fragment")
    if not wired:
        problems.append("no host is wired; run `install`")

    for key, record in wired.items():
        host = HOSTS_BY_KEY.get(key)
        if host is None:
            problems.append(f"receipt names unknown host {key}")
            continue
        pending = [
            action
            for action in plan_host(host, fragments, installed_ref, receipt)
            if action.apply is not None or action.conflict
        ]
        state = "drift" if pending else "ok"
        print(f"  {host.label}: {state}")
        for action in pending:
            problems.append(f"{host.label}: {action.conflict or action.summary}")

    if problems:
        print("\ndrift:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nall wired hosts are current")
    return 0


def undo_artifact(artifact: dict) -> str | None:
    path = Path(artifact["path"])
    kind = artifact.get("kind")
    if kind == "symlink":
        if path.is_symlink():
            path.unlink()
            return f"unlinked {path}"
        return None
    if kind == "file":
        if path.exists():
            path.unlink()
            return f"removed {path}"
        return None
    if kind == "block":
        if not path.exists():
            return None
        remainder = strip_block(path.read_text(encoding="utf-8"))
        if not remainder and artifact.get("created"):
            path.unlink()
            return f"removed {path}"
        write_file(path, remainder)
        return f"removed managed block from {path}"
    if kind == "config":
        if not path.exists():
            return None
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return f"left {path} untouched (not valid JSON)"
        existing = config.get("instructions", [])
        if not isinstance(existing, list):
            return f"left {path} untouched (`instructions` is not a list)"
        instructions = [item for item in existing if item != config_glob()]
        if instructions:
            config["instructions"] = instructions
        else:
            config.pop("instructions", None)
        if not config and artifact.get("created"):
            path.unlink()
            return f"removed {path}"
        write_file(path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")
        return f"deregistered rules glob in {path}"
    return None


def command_uninstall(args: argparse.Namespace) -> int:
    receipt = read_receipt()
    if not receipt:
        print("Nothing to remove: no receipt found.")
        return 0

    host_records: dict[str, dict] = dict(receipt.get("hosts", {}))
    targets = args.host or list(host_records)
    for key in targets:
        record = host_records.get(key)
        label = HOSTS_BY_KEY[key].label if key in HOSTS_BY_KEY else key
        if record is None:
            print(f"{label}: not wired by rules-sync")
            continue
        print(f"{label}:")
        for artifact in record.get("artifacts", []):
            if args.dry_run:
                print(f"  would revert {artifact['path']}")
                continue
            message = undo_artifact(artifact)
            print(f"  {message or 'already reverted ' + artifact['path']}")
        if not args.dry_run:
            host_records.pop(key, None)

    if args.dry_run:
        return 0

    if host_records:
        receipt["hosts"] = host_records
        write_receipt(receipt)
        if args.purge:
            still_wired = ", ".join(sorted(host_records))
            print(f"kept {store_dir()}: still wired to {still_wired}")
        return 0

    if args.purge:
        shutil.rmtree(store_dir(), ignore_errors=True)
        print(f"removed {store_dir()}")
    else:
        receipt["hosts"] = {}
        write_receipt(receipt)
        print(f"kept fragments in {store_dir()}; pass --purge to remove them")
    return 0


def observed_state(host: Host, fragments: list[Fragment]) -> str:
    """What is already in place at this host, for hosts we have not wired.

    A host can look untouched while another tool already publishes these rules
    there. Naming that here keeps the list honest about what an install would
    have to take over.
    """
    if host.mode == "link":
        target_dir = host_path(host.target)
        if not target_dir.is_dir():
            return ""
        links = [entry for entry in sorted(target_dir.iterdir()) if entry.is_symlink()]
        if not links:
            return ""
        sources = {Path(os.readlink(link)).parent for link in links}
        others = sorted(str(source) for source in sources if source != store_dir())
        if others:
            return f"{len(links)} symlink(s) here, pointing at {', '.join(others)}"
        return f"{len(links)} symlink(s) already point at the store"
    if host.mode in {"import", "inline"}:
        path = host_path(host.target)
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8")
        marks = []
        if find_block(text):
            marks.append("has our managed block")
        copies = foreign_copies(text, fragments)
        if copies:
            marks.append(f"{len(copies)} of these fragments present outside it")
        return "; ".join(marks)
    if host.mode == "config":
        alternate = host_path(host.alt_target) if host.alt_target else None
        if alternate and alternate.exists():
            registered = config_glob() in alternate.read_text(encoding="utf-8")
            return f"{alternate} in use{'' if registered else '; glob not registered'}"
        path = host_path(host.target)
        if path.exists() and config_glob() in path.read_text(encoding="utf-8"):
            return "glob already registered"
        return ""
    if host.mode == "mdc":
        target_dir = host_path(host.target)
        if not target_dir.is_dir():
            return ""
        count = 0
        for entry in sorted(target_dir.iterdir()):
            if entry.is_symlink() or entry.suffix != ".mdc" or not entry.is_file():
                continue
            try:
                text = entry.read_text(encoding="utf-8")
            except OSError:
                continue
            if managed_mdc(text):
                count += 1
        return f"{count} managed .mdc file(s)" if count else ""
    rendered = manual_dir() / f"{host.key}-user-rules.md"
    return f"text rendered at {rendered}" if rendered.exists() else ""


def command_list_hosts(args: argparse.Namespace) -> int:
    receipt = read_receipt()
    wired = receipt.get("hosts", {})
    fragments = read_store_fragments()
    width = max(len(host.label) for host in HOSTS)
    for host in HOSTS:
        state = "wired" if host.key in wired else ("detected" if detected(host) else "-")
        target = host.target or "(host UI field)"
        print(f"{host.label:<{width}}  {host.key:<12} {host.mode:<7} {state:<8} {target}")
        print(f"{'':<{width}}  {host.note}")
        current = observed_state(host, fragments)
        if current:
            print(f"{'':<{width}}  {current}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sync_rules.py",
        description="Wire shared rule fragments into agent host configurations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--host",
            action="append",
            metavar="KEY",
            help="host key to act on; repeatable. Defaults to wired hosts, else detected ones.",
        )
        subparser.add_argument(
            "--dry-run", action="store_true", help="print the plan without writing"
        )

    install = subparsers.add_parser("install", help="fetch fragments and wire hosts")
    add_common(install)
    install.add_argument("--ref", help="pin a specific revision instead of the tracked branch")
    install.add_argument("--diff", action="store_true", help="show a diff for each change")
    install.set_defaults(func=command_install)

    update = subparsers.add_parser("update", help="re-fetch the tracked branch and rewire")
    add_common(update)
    update.add_argument("--ref", help="pin a specific revision instead of the tracked branch")
    update.add_argument("--diff", action="store_true", help="show a diff for each change")
    update.set_defaults(func=command_install)

    check = subparsers.add_parser("check", help="report drift without touching anything")
    check.set_defaults(func=command_check)

    uninstall = subparsers.add_parser("uninstall", help="revert everything this script wrote")
    add_common(uninstall)
    uninstall.add_argument(
        "--purge", action="store_true", help="also delete the local fragment store"
    )
    uninstall.set_defaults(func=command_uninstall)

    list_hosts = subparsers.add_parser("list-hosts", help="show known hosts and their mechanism")
    list_hosts.set_defaults(func=command_list_hosts)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
