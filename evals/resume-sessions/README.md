# 跨来源会话接续评测

覆盖三个独立包，测试不随 Skill 安装。

```sh
python3 scripts/test-agent-neutrality.py
python3 scripts/check-agent-neutrality.py
python3 scripts/sync-resume-skills.py --check
python3 evals/resume-sessions/test_packaging.py
python3 evals/resume-sessions/test_reader.py
```

- `test_packaging.py`：把每个 Skill 单独复制到临时目录，验证资源链接不依赖兄弟目录、三份资源一致、Python 语法有效。只静态解析 reader，不导入或执行。
- `test_reader.py`：使用临时目录内的合成 JSONL/SQLite 数据验证过滤、缺口警告、错误处理和显式路径边界。运行时会导入 reader，应先完成代码审查和执行授权；不得把测试改成读取真实会话。

测试通过仅证明合成用例行为，不代表支持每个来源版本，也不证明文本已脱敏。真实来源的访问权限、仓库状态与下一步授权仍由当前会话核实。
