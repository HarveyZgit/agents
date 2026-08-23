---
name: task-dispatch-and-task-books
description: For large tasks a controller session decomposes work and dispatches it via subagents or self-contained markdown task books for new CLI agent sessions, each task naming a model and reasoning effort.
tier: core
---

## Task dispatch and task books

- For large tasks the user designates one high-level model session as the controller: it decomposes the work and dispatches subtasks outward rather than executing everything itself.
- Two dispatch channels: subagents of the controller session, or new independent CLI agent sessions the user opens manually.
- To dispatch to a new session, write a markdown task book to a local temp directory; the user opens a new session that reads and executes it. The new session shares zero context, so each task book must be self-contained: goal, constraints, relevant file paths, verification steps, and done criteria.
- Each task dispatched to a new session names a session model — claude opus 5, claude opus 4.8, grok 4.6, gpt 5.6 sol / terra / luna — and a reasoning effort: mid / high / xhigh.
