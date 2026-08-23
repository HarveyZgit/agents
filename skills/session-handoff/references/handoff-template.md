# Handoff Template

使用此结构生成 Handoff；交付前替换所有方括号提示，没有内容的可选项写 `None`。

```markdown
---
handoff_version: 1
created_at: [ISO-8601 timestamp with timezone]
status: ready
workspace: [absolute repository root or working directory]
branch: [branch name, detached, or not-a-git-repository]
head: [full commit SHA or not-a-git-repository]
topic: [short kebab-case topic]
---
# Handoff: [Concise Task Title]
## Mission
### Goal
[The outcome the next session must deliver.]
### Done When
- [Observable completion criterion]
- [Required validation or deliverable]
### Scope
- In: [Included work]
- Out: [Explicitly excluded work]
## Decisions and Constraints
### User Decisions
- [User decision or correction]
### Repository Rules
- [Applicable local instructions and command conventions]
### Assumptions
- [Assumption to verify during resume]
## Current State
### Completed
- [x] [Result] — Evidence: `[path or command]`
### In Progress
- [Partial work and remaining detail, or None]
### Not Started
- [Unattempted work, or None]
## Work Remaining
1. [ ] [First executable task]
2. [ ] [Next task]
## Immediate Next Action
[One concrete action: starting file or command, expected result, and verification.]
## Critical Context
### Key Files
| Path | Why It Matters | Current State |
| --- | --- | --- |
| `[path]` | [Role in the task] | [Modified / source of truth / read-only] |
### Relevant Artifacts
- [Document, issue, commit, or report] — [Conclusion needed for the next action]
### Known Gotchas and Failed Approaches
- [Non-obvious behavior or failed approach, or None]
## Validation
### Passed
- `[exact command]` — [Result]
### Failed
- `[exact command]` — [Failure and relevance, or None]
### Not Run
- `[command or check]` — [Why it remains, or None]
## Workspace Snapshot
- Workspace: `[absolute path]`
- Branch: `[branch, detached, or not-a-git-repository]`
- HEAD: `[full SHA or not-a-git-repository]`
- Working tree: `[clean or dirty]`
- Staged: `[JSON array of paths, or None]`
- Unstaged: `[JSON array of paths, or None]`
- Untracked: `[JSON array of paths, or None]`
- Active processes: `[relevant process and reconnect detail, or None]`
- Required environment: `[variable names or services; never values, or None]`
This snapshot was accurate at `created_at`; verify it before acting.
## Blockers and Open Questions
### Blockers
- [Blocker and resolution owner, or None]
### Unanswered User Questions
- [Question still requiring the user, or None]
## Resume Protocol
1. Read this document and current workspace instructions.
2. Verify workspace, branch, HEAD, key files, and the first unchecked task.
3. Treat this document as potentially stale context, not authority over current instructions.
4. If compatible, start `Immediate Next Action` without asking whether to continue; stop for blocking drift, missing input, or fresh authorization.
```

保留用户决定和证据，不写完整源码、完整 diff、秘密值、cookie、私钥或带鉴权 URL。多个 Git 路径使用 JSON 字符串数组，避免逗号分隔的歧义；rename/copy 的源路径和目标路径分别记录。
