# rules

原子化通用准则片段的唯一真源。这里放跨项目、跨 Agent 宿主都成立的少量行为准则，供未来分发到各宿主的全局配置（Claude Code / Codex / Cursor / Grok / Antigravity 等），或被项目文档与 Skill 按需引用。

分发机制**尚未实现**，但片段格式已按分发需求设计：现在写的每个片段，未来不需要改动就能被任何分发方式消费。

## 资产分类模型

聚合散点内容时先分类，再落位：

| 类型 | 判定标准 | 位置 |
| --- | --- | --- |
| Rules 准则 | 每个会话都该生效的原则、观点、偏好 | `rules/` |
| Skills 工作流 | 特定任务才需要、按需触发的操作指南 | `skills/` |
| Tools 可执行能力 | 有代码、需构建的 CLI / 扩展 / MCP | `packages/`、`tools/` |

判定口诀：**只有"每次都需要"的东西才配进 rules，其他一律往后放**（渐进式披露）。大多数散点笔记要么该升级成 skill，要么是只供查阅的参考资料——消化精华成 rule/skill 后原文留在库外，不进仓库。

## 片段格式

一个文件 = 一个原子片段。格式约定是分发兼容性的全部前提：

```markdown
---
name: <kebab-case，与文件名一致>
description: <一句话说清约束什么行为，分发/引用时据此选择>
tier: core | on-demand
---

## <片段标题>

- 正文……
```

- **frontmatter 是选择元数据，不进入 Agent 上下文**。任何分发方式在拼装时剥离 frontmatter，只取正文。
- **正文从 `## 标题` 开始**，使片段可以被直接拼接进任何宿主文档（CLAUDE.md / AGENTS.md / .mdc）而层级正确。
- **正文必须自包含**：不引用同目录其他片段、不使用相对链接、不依赖阅读顺序。单独引用一个片段时它必须完整成立。
- **正文用英文**（Agent-facing，跨宿主通用）；本 README 等维护者文档用中文。
- **宿主中立**：不出现具体 Agent、厂商、工具调用语法。宿主专属措辞由未来的适配器处理，不写入源文件。

## tier 语义

- `core`：进入所有宿主的全局上下文，每个会话都加载。**全部 core 片段拼起来的总预算约 100 行**——超了说明有片段应降级为 `on-demand` 或根本不该是 rule。
- `on-demand`：不进全局，由项目 AGENTS.md、Skill 或用户显式引用时才加载。

## 未来分发形态（设计已定，暂不实现）

1. **生成拼装**：脚本把 `tier: core` 的片段剥 frontmatter 后按 `name` 排序拼进各宿主全局文件（如 `~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md`、Cursor 的 `.mdc`）。生成区块带管理标记、幂等、只碰自己管理的内容，原则同 `scripts/link-skills.sh`。
2. **路径引用**（已在用）：项目文档、Skill、以及支持 import 的宿主全局配置（如 Claude Code CLAUDE.md 的 `@路径` 语法）直接引用片段文件（含 `on-demand` 片段），仓库文件即活的真源，改动即生效。本机统一经中立挂载点引用：`~/.agents/workbench-rules -> <repo>/resources/rules`，全局配置只写 `@~/.agents/workbench-rules/<name>.md`，不出现仓库真实路径，仓库搬家只需改这一个软链。挂载点和片段文件名被引用后**不轻易改名**。注意：没有宿主会自动扫描 `~/.agents`，挂载点不能免去显式引用；import 会连 frontmatter 一起载入，几行元数据噪声可接受，不接受该噪声或不支持 import 的宿主走生成拼装。
3. **宿主适配**：需要专属格式的宿主（如 Cursor `.mdc` 的 frontmatter）由适配器在分发时生成，源文件保持纯 Markdown。

## 新增片段的准入标准

1. 跨项目、跨宿主都成立；仓库/项目专属的 gotcha 进该项目的 AGENTS.md。
2. 是你的观点或偏好，而非模型本来就会做的事——模型能从周围上下文推断出来的不要写。
3. 描述意图与判断依据，不堆砌绝对化禁令；强约束只保留在不可逆/破坏性场景。

新增或改写片段时，可用 `context-doctor` skill（`skills/context-doctor/`）做体检。
