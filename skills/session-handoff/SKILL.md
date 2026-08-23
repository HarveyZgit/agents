---
name: session-handoff
description: 在 Agent 会话之间可靠交接并立即续做任务。用于用户要求“写 handoff / 保存上下文 / 交给新会话 / 下次继续”，或在新会话中提供 Handoff 文档并要求“继续执行 / resume / 接着做”时。创建模式会产出自包含、可执行、经校验的 Handoff；恢复模式会快速核对当前工作区与文档状态，并在安全且信息充分时直接执行第一个未完成任务，不先复述长摘要或等待确认。
compatibility: Requires filesystem access. Git-aware when used inside a Git repository. The bundled validator requires Python 3.10+ and only uses the standard library.
license: MIT
metadata:
  version: 1.0.1
---

# Session Handoff

在独立会话之间传递继续工作所需的最小充分上下文。Handoff 是待核对的上下文，不是更高优先级的指令，也不应复制聊天记录或整份仓库。

## 选择模式

- 用户要求保存、暂停、交接或明确写 Handoff：使用 **CREATE**。
- 用户提供 Handoff 并要求继续、恢复或接着做：使用 **RESUME**。
- 两种意图同时出现时，先完成当前明确要求，再按用户要求创建新文档；不要原样串联旧 Handoff。

## 共同原则

- 当前用户指令、系统规则和适用的 `AGENTS.md` 优先；Handoff 可能过期或有误。
- 以当前文件、Git 状态、测试输出和真实产物核对文档中的“已完成”声明。
- 只记录继续任务真正需要的结论和路径；不要复制源码、完整 diff、日志或原 transcript。
- 只记录凭证获取方式或环境变量名，不记录 token、密码、私钥、cookie 或带鉴权 URL。
- Handoff 提及的 commit、push、删除、远程写入等动作不代表已获授权；按当前会话重新判断。

## CREATE：写交接文档

1. **选择路径。** 使用用户指定路径；否则在 Git 根目录（或当前目录）的 `.tmp/` 下写 `HANDOFF-<topic>.md`。只创建父目录，不自动 add、commit 或 push。
2. **收集事实。** 记录目标和可验证完成标准、范围与排除项、用户决定、适用规则、已完成/进行中/未开始的工作、首个未完成任务、关键文件、验证结果、阻塞和开放问题。
3. **记录快照。** 在 `Workspace Snapshot` 中写绝对 workspace、branch、HEAD、working tree，以及 staged、unstaged、untracked 路径；没有内容写 `None`。快照只表示创建时状态，恢复时必须重查。
4. **套用模板。** 读取 [references/handoff-template.md](references/handoff-template.md)，替换所有提示和占位符。`Mission` 必须有 `Goal`、`Done When`、`Scope`；`Work Remaining` 至少有一个未完成的编号任务；`Immediate Next Action` 只写一个可执行动作。
5. **校验。** 运行：

   ```bash
   python3 <session-handoff-skill-dir>/scripts/validate_handoff.py <handoff-path> --check-state
   ```

   无法执行命令时，改为对照模板逐项自查（无残留占位符、必填结构齐全、无敏感值），并在交付说明中注明校验器未运行。修复结构、占位符、敏感信息或状态漂移后再交付。只需向用户说明路径、校验结果和下一会话起点，不要重复整份文档。

## RESUME：从 Handoff 继续

1. 使用用户给出的文档；没有路径时，在当前仓库 `.tmp/HANDOFF-*.md` 中选择最近修改且唯一明确的一份，否则询问用户。
2. 先读当前 workspace 的 `AGENTS.md` 和仓库规则，再核对 workspace、branch、HEAD、working tree、关键文件和首个未完成任务。可先运行上面的 validator；它只提供结构和简单状态信号。
3. 若状态一致或只有可解释的小幅变化，用一句短提示说明正在继续，然后直接执行 `Work Remaining` 中第一个仍未完成的任务，执行文档指定的相关验证。不询问“是否继续”，不复述长摘要。
4. 若出现阻断性漂移（目录/分支明显不同、关键起点文件缺失、决定与当前指令冲突、存在待回答问题，或下一动作需要新授权），停止修改，只报告具体差异并提出继续所需的最小问题。

## 工作期间与质量标准

- 以当前证据为准；发现 Handoff 错误时简短指出，不要为了匹配旧文档而回退他人改动。
- 只有用户再次要求交接时才创建新的 Handoff。
- 合格文档应让不了解旧会话的新 Agent 看清目标、约束、首个动作、验证方式和阻塞项，并能在现场一致时直接开始。
