---
name: context-doctor
description: 用新一代模型的 context engineering 原则诊断并改写 Agent 上下文资产（skill、CLAUDE.md/AGENTS.md、rules 片段、工具描述、系统提示词）。当用户要求 review/瘦身/精简/简化/优化某个上下文资产、新写此类资产前对齐规范、做 context engineering、或怀疑 Agent 被过度约束时使用。Use when asked to review, slim down, simplify, or optimize a context asset. 只处理上下文资产本身，不负责业务代码 review。
metadata:
  version: 1.0.0
---

# context-doctor

Diagnose and rewrite agent context assets: skills, project instruction files (CLAUDE.md / AGENTS.md / host rules files), atomic guideline fragments, tool descriptions, and system prompts.

Core premise: for current frontier-class models, many hard constraints, worked examples, and repetitions in older context assets compensate for model weaknesses that no longer exist. Removing them frees context, reduces instruction conflicts, and widens the exploration space. The six principles behind every diagnosis live in [references/principles.md](references/principles.md) — read it before diagnosing or rewriting.

To author a new asset rather than diagnose an existing one: read principles.md, write directly against it, then self-check the result with its red-flag list. The workflow below targets existing assets.

## Workflow

### 1. Establish loading mode and consumer capability

Determine two things before diagnosing:

- **When the asset enters context**: every session (global rules, CLAUDE.md), on demand (skills), or attached to a tool. The more frequently it loads, the stricter the admission bar and the larger the payoff of slimming.
- **Which models will consume the asset**: frontier-class only, weaker or open-weight models too, or unknown. This selects normal or conservative application of the principles (defined in the capability-sensitivity note of principles.md). When unknown, assume the conservative case.

If you can enumerate the assets loaded alongside the target (listed by the user, or discoverable in the working directory: CLAUDE.md, AGENTS.md, rules files), include them in a cross-asset conflict check. If you cannot, state in the report that only single-asset diagnosis was performed and the conflict dimension is uncovered.

### 2. Diagnose

Check the asset against the six principles and the red-flag list in [references/principles.md](references/principles.md). Output a structured report; each finding has:

- Location (`file:line`)
- Type (over-constraint / redundant example / should be deferred / repetition / conflict / states the obvious / spec form upgradable)
- Severity (high / medium / low) — scale by loading frequency and blast radius: a conflict in an every-session asset is high; deferrable verbosity is low
- Rationale: why the model does not need this, or why it belongs in a different place or form
- Action (delete / rewrite as intent / move to an on-demand reference file / split into a separate skill / keep)

Deliver the report in the user's language.

### 3. Preservation boundary (apply before any deletion)

Never remove for the sake of slimming:

- Protections around irreversible or destructive operations (deleting data, pushing, publishing, spending money).
- Security and compliance boundaries.
- The maintainer's own opinions, preferences, and codebase gotchas — the most valuable content in a context asset. Test: if the model can infer it from surrounding context, cut it; if it cannot and it matters, keep it.
- Structural constraints the repository already declares (e.g. host-neutrality requirements).
- Compensating constraints written deliberately for weaker consumer models.

When uncertain, downgrade the action: from delete to rewrite-as-intent, or to moving the content behind on-demand loading.

### 4. Rewrite

Default to report first; edit files only after the user confirms. If the user asked for direct edits up front, edit and then present a before/after summary (line counts, which categories were removed, what was kept). While rewriting:

- Confine edits to the target asset plus any relocation targets the report prescribes (new reference files, a split-out skill); do not drift into unrelated files.
- The result must still satisfy its own format conventions (skill frontmatter, fragment atomicity, and similar).
- Check a skill's `description` separately: does it say what the skill does and when to trigger it? This determines trigger accuracy.
- When the user wants changes in batches, apply findings in severity order.

### 5. Verify

- Walk the report: every finding handled, nothing silently lost — anything removed is either inferable by the consumer or relocated to an on-demand position.
- If the asset's repository has an eval suite covering it, run it; if you cannot execute commands, ask the user to run it and report back. For a large deletion with no eval backing, recommend adding a minimal eval first.
