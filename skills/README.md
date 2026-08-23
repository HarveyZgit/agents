# skills

独立 workflow Skill 的真源。`npx skills` 会直接扫描这个目录。

## 宿主中立

- Skill 源文件不得固定某个 Agent、CLI、厂商、账号、邮箱、运行时目录或专属工具调用语法。
- 需要独立审查、委派、状态存储等能力时，描述能力契约与失败行为，不写死某个宿主的工具名。
- Skill 源文件不猜测安装目录。分发交给 `npx skills`。

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
