---
name: rules-sync
description: Install, update, verify, or remove the maintainer's shared core rule fragments in this machine's agent host configurations. Use whenever the user asks to install, update, re-sync, or uninstall their rules, sets up a new machine or a newly added agent host, wants global rules wired to the shared fragments, asks whether the installed rules are current, or wonders why a global rule is not taking effect. Also use for phrasings like "装一下我的 rules"、"更新 rules"、"卸载 rules"、"这台机器的全局规则怎么配".
---

# rules-sync

Wire the `tier: core` rule fragments published by the maintainer's agents repository into every agent host on this machine, so each host loads the same rules from one shared source instead of a hand-maintained copy per host.

## The adapter owns host knowledge

`scripts/sync_rules.py` is the only component that knows which hosts exist, where their global configuration lives, and which mechanism each one supports. Drive it and report what it did; do not open host configuration files yourself and do not reimplement its wiring by hand. Hand edits drift from the receipt the script keeps, and the next `check` or `uninstall` can then no longer reason about what is installed.

Fragments land in a neutral store (`~/.agents/rules` by default, overridable with `AGENT_RULES_HOME`). Hosts that can follow a live reference get a symlink, an import directive, or a config glob pointing at that store, so a later `update` reaches them without touching their config again. Only hosts that expand nothing receive inlined text, and hosts whose global rules live in a UI field get rendered text plus a manual step.

## Commands

```sh
python3 scripts/sync_rules.py list-hosts               # known hosts, mechanism, detected/wired state
python3 scripts/sync_rules.py install --dry-run        # plan only; add --diff for exact edits
python3 scripts/sync_rules.py install                  # fetch the tracked branch and wire hosts
python3 scripts/sync_rules.py update                   # same, to pick up newer fragments
python3 scripts/sync_rules.py check                    # drift report; non-zero on drift
python3 scripts/sync_rules.py uninstall                # revert every recorded change
```

`--host <key>` (repeatable) narrows any command to specific hosts. With no `--host`, the script acts on hosts already wired, falling back to the ones it detects on this machine. `uninstall --purge` also deletes the local store; without it the fragments stay, so a later `install` is cheap.

## How to run a request

1. Run `list-hosts` when the user has not named hosts, so the plan covers what actually exists here rather than an assumption.
2. Run the mutating command with `--dry-run` first and show the user which hosts change and how. Global rule files are configuration the user reads and edits themselves, so they should recognize every edit before it happens. Skip the preview only when the user has already approved this exact plan.
3. Apply, then report per host: the mechanism used, the file touched, and the result.
4. Surface any manual step verbatim, including the path of the rendered text. A host reporting success while its rules are still unpasted is the one failure mode the script cannot detect.
5. On `check` drift, prefer `install`/`update` to repair it. Editing the managed block by hand fixes the symptom and leaves the receipt stale.
6. If a command refuses because a target path holds something the script did not create, nothing has been written yet. Report the listed paths, let the user move them aside, then rerun.

Never remove a host's wiring without the user asking for it. `install --host X` leaves other hosts alone by design, so a narrow request stays narrow.

## Maintaining the adapter

`SOURCE_REF` at the top of the script is the tracked branch, so publishing fragments needs no change to the script: the next `update` fetches the new tip. Each install records the commit it resolved to, so `check` reports a moved branch as drift; when the remote cannot be reached it says so and still checks the wiring. Use `--ref <sha>` when a run must be reproducible.

Each entry in the script's `HOSTS` table carries the capability its mode depends on. Re-check that capability before switching a host's mode: the mechanism is a consequence of what the host can follow, not a preference.
