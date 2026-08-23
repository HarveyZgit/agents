---
name: compact-prompt-convention
description: When the user asks for a "compact prompt", output a prompt text for them to pass to their host's manual context-compaction command.
tier: core
---

## Compact prompt convention

- The user compacts context manually via the host's compact command (e.g. `/compact <prompt>`).
- When the user asks to "compact prompt" (or for a compact prompt), the deliverable is a single prompt text they will pass to that command: instruct the compaction on what to carry forward — current goal, key decisions and constraints, work state, and next steps for this session.
- Do not run compaction yourself and do not summarize the conversation in place of the prompt.
