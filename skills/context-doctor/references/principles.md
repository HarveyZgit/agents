# Context engineering principles

Six "then → now" shifts, each with diagnostic notes. They apply to frontier-class models regardless of vendor.

**Capability sensitivity.** Principles 3 (progressive disclosure), 4 (say it once), conflict elimination, and removal of statements of the obvious hold for consumers of any capability level. Principles 1 and 2 assume a high-judgment consumer: for assets consumed by weaker or unknown models, apply them conservatively — state the intent and keep the hard constraint and key examples alongside it (the finding's action is keep, or rewrite with constraints retained; never delete), because for those models the constraints are still necessary compensation.

## 1. Rules → judgment

Absolute prohibitions (NEVER / ALWAYS / must not) are mostly worst-case guards for older models. For some inputs they are necessarily wrong, and they force the model to burn reasoning on conflicting instructions. Rewrite direction: replace the rule with **intent plus an anchor for local judgment**.

Canonical rewrite (the comment rule):

> Old: In code: default to writing no comments. Never write multi-paragraph docstrings… one short line max.
> New: Write code that reads like the surrounding code: match its comment density, naming, and idiom.

Diagnostic notes: count absolute phrasings in the target; for each, ask "is there a reasonable input for which this rule is wrong?" — if yes, it is a rewrite candidate. Exceptions stay strong: irreversible or destructive operations and security boundaries keep their hard constraints, regardless of consumer capability.

## 2. Examples → interface design

Worked usage examples confine the model to the space the examples sketch. Expressiveness should come from **the interface itself**: parameter names, enum values, one-line constraints. Example: a todo tool whose status enum is `pending / in_progress / completed` plus the single sentence "only one task in_progress at a time" replaced roughly 9,100 characters of when-to-use lists and worked examples.

Diagnostic notes: find worked-example blocks and "for instance, call it like this" passages. If the information can be carried by parameter naming, enums, or a one-line constraint, delete the example and improve the interface description. Distinguish: contrast examples that encode taste (like the rewrite pair above) are the payload of a rubric and stay.

## 3. Everything up front → progressive disclosure

A context asset is not a vault of everything the model might miss; it is a tree loaded on demand:

- The entry file (CLAUDE.md, the SKILL.md body) holds only high-frequency essentials and pointers to detail.
- Low-frequency detail moves into reference subfiles, separate skills, or deferred tool definitions.
- CLAUDE.md tokens belong to **gotchas invisible from the code**, not to restating what the file system or README already shows.

Diagnostic notes: for each passage ask "what fraction of sessions needs this?" — defer what is low-frequency and chunky. A skill body over roughly 100 lines with no reference subfiles is a structural red flag.

## 4. Repeat yourself → say it once

Older models favored instructions near the end of context, so the same instruction was written in both the system prompt and the tool description. Newer models do not need this: **an instruction lives in the one place closest to its point of use** (a tool's usage belongs in the tool description); delete the other copies.

Diagnostic notes: search across files for synonymous instructions; when a constraint appears in more than one place, keep the copy closest to the point of use.

## 5. Manual memory → auto-memory

Stop instructing users to pile session memories into CLAUDE.md by hand. Where the host has a memory mechanism, memory belongs there; what remains in CLAUDE.md should be stable project facts, not session residue.

Diagnostic notes: find "we changed X last time" / temporary-agreement content — delete what is stale, rewrite what is stable into a project fact.

## 6. Simple specs → rich references

Models consume far richer referents than markdown plan files, and **code-shaped references have the highest fidelity**:

- An HTML mockup beats a prose description of a design, and beats a screenshot.
- A detailed test suite, or a function in another codebase to port, is itself a spec.
- A rubric handed to a verifier agent is how taste gets encoded.

Diagnostic notes: where the asset describes expected output in long prose, consider replacing it with a pointer to code, tests, a mockup, or a rubric.

One nuance for system prompts: a self-built agent harness's system prompt carries the product context and is where deliberate investment belongs — diagnose it for conflicts and redundancy, but do not treat raw size reduction as the goal there.

## Quick red flags

- High density of absolute prohibitions, mostly unrelated to irreversible operations
- Worked-example blocks, "example invocation" passages
- Long entry file (≈100+ lines) with no reference subfiles
- The same instruction repeated across files
- Statements of what the model can see from the code or file system
- Conflicting instructions (typically "global says A, skill says B")
- Stale session-residue memories
- Prose descriptions of specs that code or tests could express

## Stop-loss for slimming

Slimming is not the goal; **low noise, no conflicts, on-demand loading** is. Every deletion must answer "why does the consumer not need this?" — if it cannot, take the downgrade path (rewrite as intent, move to an on-demand position) instead of deleting. Do large cuts only with an eval as a safety net: even an 80%+ cut of a production system prompt has proven safe, but only when coding evals confirmed no regression.
