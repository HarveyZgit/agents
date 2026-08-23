# Agents repo guide

This repository is the source of truth for standalone Agent Skills, host-neutral rules, and skill evals. Keep every asset independently understandable, testable, and installable.

The repository is written primarily for a Chinese-speaking maintainer. User-facing documentation should normally be Chinese; use English when it is conventional for code, package metadata, or commit messages.

## Source of truth

- Skills live in `skills/<name>/SKILL.md`. Install with `npx skills add HarveyZgit/agents`.
- Rules live in `rules/` and reach a machine's hosts through the `rules-sync` Skill. See [rules/README.md](rules/README.md).
- Evals live in `evals/<name>/` and must not be installed with a Skill. See [evals/README.md](evals/README.md).
- Tools, CLIs, and package-bound Skills stay in [HarveyZgit/workbench](https://github.com/HarveyZgit/workbench).

## Working rules

- Keep reusable AI assets host-neutral: do not hard-code an Agent/CLI/vendor identity, email, proprietary tool invocation, runtime directory, or default install target. The single exception is the host adapter under `skills/rules-sync/`, whose purpose is to name hosts and their configuration paths; `scripts/check-agent-neutrality.py` exempts exactly those files, and the Skill body shipped with them stays neutral.
- Skill sources must not guess their own install directories. Distribution is `npx skills`.
- Keep changes narrow. Update the relevant README when a public boundary changes.

## Verification

```sh
python3 scripts/test-agent-neutrality.py
python3 scripts/check-agent-neutrality.py
```
