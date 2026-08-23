# session-handoff evals

这里保留 `session-handoff` 的最小行为评测；输入 fixture 与 Skill 源码分离：

- Skill：`skills/session-handoff/`
- Evals：`evals/session-handoff/`
- 场景：CREATE、RESUME-compatible、RESUME-blocking-drift

`evals.json` 中的 `files` 相对本目录解析。`fixtures/` 是可复用输入，不包含运行输出；skill-creator 的 iteration workspace 和 review 页面应放在临时目录，不纳入仓库。

## 本地验证

```sh
python3 evals/session-handoff/tests/test_validate_handoff.py
python3 evals/session-handoff/tests/test_setup_eval_workspace.py
```

如需运行 skill-creator 评测，使用 `skills/session-handoff` 作为 Skill path，并把生成的 workspace 指向仓库外临时目录。
