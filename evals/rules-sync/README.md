# rules-sync evals

`rules-sync` 的行为评测。这个 Skill 会写宿主的全局配置，所以每个场景都在临时目录里造一个假 home，评测过程**不允许触碰真实 home**。

- Skill：`skills/rules-sync/`
- Evals：`evals/rules-sync/`
- 场景：fresh（首次安装）、drifted（漂移后修复）、installed（按宿主收窄卸载）

`scripts/setup_sandbox.py` 从适配器的宿主表读取布局，因此这里不重复宿主知识，也不会与 Skill 脱节。沙箱会给拼装型和配置型宿主预置既有内容，用来暴露覆盖用户配置的行为。`installed` 和 `drifted` 场景需要联网（脚本按固定 revision 拉取片段）。

## 本地验证

```sh
python3 evals/rules-sync/tests/test_sync_rules.py
python3 evals/rules-sync/tests/test_setup_sandbox.py
```

`test_sync_rules.py` 覆盖适配器动用户文件的那几个原语：托管块的写入/移除、配置项的注册/注销、按片段写入宿主自有 frontmatter 的文件、`created` 标记的粘性、以及经软链写入。这些回归会静默损坏宿主配置，所以离线单测比端到端评测更靠得住。

## 运行评测

```sh
python3 evals/rules-sync/scripts/setup_sandbox.py fresh /tmp/<name>
```

脚本打印沙箱路径；后续命令一律带 `HOME=<该路径>`。skill-creator 的 iteration workspace 与 review 页面放到仓库外的临时目录。
