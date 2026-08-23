# agents

个人 Agent 资产目录：Skills、Rules、Evals。可构建的工具仍在 [HarveyZgit/workbench](https://github.com/HarveyZgit/workbench)。

```text
skills/     # 独立 workflow Skill，npx skills 直接扫这里
rules/      # 每个会话都该生效的准则片段
evals/      # 按 Skill 隔离的评测，不随 Skill 安装
scripts/    # 宿主中立检查
```

## 安装 Skills


```sh
npx skills add HarveyZgit/agents
npx skills add HarveyZgit/agents --skill eli5
npx skills add HarveyZgit/agents -g
npx skills add HarveyZgit/agents --list
```

包绑定型 Skill（例如 workbench 里的 `markdown-comment`）不在这里。

## 新增 Skill

1. 建 `skills/<name>/SKILL.md`，写好 `name` / `description`（做什么 + 什么时候用）。
2. 需要评测时在 `evals/<name>/` 加定义，不要把评测文件放进 `skills/`。

## 验证

```sh
python3 scripts/test-agent-neutrality.py
python3 scripts/check-agent-neutrality.py
```
