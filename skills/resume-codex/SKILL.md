---
name: resume-codex
description: 从 Codex 的近期会话、原生会话 ID、标题关键词或导出路径恢复上下文，在当前 Agent 中接着做。用户说“从 Codex 继续”或切换工具后要接续任务时使用；用于读取历史，不启动来源工具。
---

# resume-codex

读取并遵循 [references/CORE.md](references/CORE.md)，来源参数为 `codex`。会话引用取自用户当前请求，可省略；不要假定存在宿主专用的参数变量。

随包 reader：[scripts/session_reader.py](scripts/session_reader.py)。来源与许可说明见 [references/PROVENANCE.md](references/PROVENANCE.md)。
