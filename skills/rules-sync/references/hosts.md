# 宿主接线依据

这份文档和 `scripts/sync_rules.py` 是仓库里唯一具名宿主的地方，中立性检查对二者开了窄口子。改动宿主表前先读这里：每个宿主的模式都由一项能力决定，能力变了模式就该变。

选择原则：**能走活引用就不要拼装文本**。symlink / import / config glob 三种模式下，`update` 只需刷新中立目录里的片段，宿主配置不用再动；inline 模式每次都要重写宿主文件，只在宿主什么都不展开时才用。

## 现有宿主

| 宿主 | 模式 | 落点 | 依据 |
| --- | --- | --- | --- |
| Claude Code | link | `~/.claude/rules/<name>.md` | 用户级 rules 目录对所有项目自动生效，官方明确支持 symlink 且能处理循环链接。无 `paths` frontmatter 的文件无条件加载，所以剥掉 frontmatter 的正文正好可用 |
| Gemini CLI | import | `~/.gemini/GEMINI.md` | `@path` 支持绝对路径，启动时展开进 memory |
| Codex | inline | `~/.codex/AGENTS.md` | 唯一不展开 `@path` 的宿主，会当字面文本 |
| OpenCode | config | `~/.config/opencode/opencode.json` 的 `instructions` | 该数组支持 glob，指向中立目录即可保持活引用 |
| Cursor | manual | 渲染到 `<store>/.out/cursor-user-rules.md` | 全局规则只存在于 Customize → Rules 的纯文本框里，没有文件入口 |

## 会改变结论的变化

- **Codex 支持 `@` 展开**（openai/codex [#17401](https://github.com/openai/codex/issues/17401)、[#6038](https://github.com/openai/codex/issues/6038) 仍 open）→ 改成 import，`~/.codex/AGENTS.md` 里只留 import 行。
- **Cursor 正式支持 `~/.cursor/rules/*.mdc`**（目前论坛口径是「部分支持」：必须有 frontmatter，且只在项目位于 home 之下时才会被向上发现）→ 改成生成 `.mdc` 的 link/生成模式。当前不生成 `.mdc`，因为写出去的文件可能静默不加载，比明确要求手工粘贴更糟。
- **OpenCode 的 `instructions` 改为跨层级合并** → 现状是「最近的一份配置整体覆盖」，项目级 `opencode.json` 只要也写了 `instructions` 就会遮蔽全局那条 glob。这是 config 模式已知的窗口；真被遮蔽得频繁，就退回 inline 写 `~/.config/opencode/AGENTS.md`（该文件与项目文件是拼接关系，不会被遮蔽）。

## 未纳入的宿主

`rulesync` 一类工具覆盖 40+ 宿主，这里只接维护者实际在用的五个。新增宿主的门槛是「这台机器上真的会开」，不是「生态里存在」。

## 分发链条

Skill 本体由 `npx skills add HarveyZgit/agents --skill rules-sync` 分发（skills CLI 只认 `SKILL.md`，没有 rules 概念，所以 rules 由本 Skill 自己拉取）。片段由脚本按 `SOURCE_REF` 从 GitHub tarball 取，不依赖 git、不需要鉴权、不要求本地有仓库 clone。
