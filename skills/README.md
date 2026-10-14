# skills

独立 workflow Skill 的真源。`npx skills` 会直接扫描这个目录。

## 宿主中立

- Skill 源文件不得固定某个 Agent、CLI、厂商、账号、邮箱、运行时目录或专属工具调用语法。
- 需要独立审查、委派、状态存储等能力时，描述能力契约与失败行为，不写死某个宿主的工具名。
- Skill 源文件不猜测自己的安装目录。分发交给 `npx skills`。
- `rules-sync/` 的宿主适配器可具名宿主及配置位置，中立性检查只豁免明确列出的适配文件。`resume-claude`、`resume-codex`、`resume-cursor` 可具名待读取的来源格式与数据路径，但不得绑定执行宿主；检查器只允许指定 reader 中精确的来源诊断行，其他规则照常检查。所有 SKILL.md 仍受检查。

包绑定型 Skill 不放这里，随所属 package 维护。

## 目录约定

```
skills/<skill-name>/
  SKILL.md          # 必需：frontmatter(name/description) + 指令正文
  scripts/          # 可选
  references/       # 可选
  assets/           # 可选
```

评测放在 [`evals/<skill-name>/`](../evals/README.md)，不要放进会被安装的 Skill 目录。

## 跨工具接续

三个独立入口分别读取对应来源，在当前 Agent 中继续：`resume-claude`、`resume-codex`、`resume-cursor`。每个目录都有完整的 reader 与 references，任选一个安装即可，不需要兄弟目录或隐藏运行时变量。

维护真源是 `resume-claude/scripts/session_reader.py` 与其 `references/` 下的 CORE、formats、PROVENANCE。修改后运行 `python3 scripts/sync-resume-skills.py` 同步其余两包；`--check` 只检查漂移。共享仅发生在仓库维护阶段，安装后没有跨目录依赖。

本组改编自用户提供的导出包；包中未附上游许可，不应推断为 Apache/MIT。见各包 [来源说明](resume-claude/references/PROVENANCE.md)，公开再分发前须确认权利。测试与已知覆盖在 [evals/resume-sessions](../evals/resume-sessions/README.md)。
