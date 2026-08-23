---
name: scope-and-final-state-hygiene
description: Deliver only the requested outcome; keep the final diff, comments, and PR description free of everything else.
tier: core
---

## Scope and final-state hygiene

- Implement only the requested outcome, its direct dependencies, and relevant validation. Do not add adjacent improvements, speculative abstractions, fallbacks, compatibility layers, caches, or configuration without an observed requirement.
- Before handoff, inspect the final diff and remove unrelated changes, orphaned code, and artifacts from discarded approaches.
- Comments explain only non-obvious rationale at the owning boundary. Include constraints or invalidation conditions only when maintainers need them. Do not restate the code, preserve intermediate attempts, or list speculative future work.
- PR/MR descriptions state the final behavior and only material rationale or trade-offs that reviewers cannot recover from the diff. Do not mention intermediate attempts, reverted approaches, or states that were never merged.
