# evals

Agent Skill 的统一评测目录。评测定义、夹具和必要的评测辅助脚本按 Skill 名称隔离：

```text
evals/<skill-name>/
├── evals.json
├── fixtures/
├── scripts/
└── tests/
```

## 边界

- `skills/<skill-name>/` 只保留安装后运行该 Skill 必需的文件。
- `evals/<skill-name>/` 保存开发期评测资产，不随 Skill 全局安装。
- `evals.json` 中的 `files` 路径相对当前 Skill 的 eval 根目录。
- 评测命令从仓库根目录执行，避免依赖已安装 Skill 的软链位置。
- `skill-creator` 生成的 workspace、benchmark、grading 和静态 review 属于临时运行产物，默认写到仓库外，不纳入版本控制。
