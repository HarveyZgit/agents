# 来源格式与限制

这里只描述读取对象，任何支持运行随包 Python reader 的 Agent 都可作为执行宿主。

- `claude`：Claude Code 的 JSONL；自动发现使用 `CLAUDE_CONFIG_DIR` 或用户目录下 `.claude/projects`。默认只发现当前项目目录；原生 ID 可跨项目查找。恢复主链、并行工具记录、保留片段及裁剪信息。
- `codex`：Codex 的 rollout JSONL / `.jsonl.zst`；自动发现使用 `CODEX_HOME` 或用户目录下 `.codex`，优先读取 `state_*.sqlite`，否则扫描 `sessions`。原生 ID 查找也包括 `archived_sessions`。无可用索引时，目录扫描不会为发现而解压 `.zst`；压缩会话需可用数据库索引、原生 ID 或显式路径。读取数据库为只读；显式路径须符合 rollout 文件名约定。
- `cursor`：Cursor 的 JSONL、会话目录下 `store.db` / `meta.json`，以及自动发现的桌面 `state.vscdb`。自动发现涉及用户目录下 `.cursor` 和平台应用数据目录。桌面数据库需要通过原生 ID 选会话，不支持直接把 `state.vscdb` 当成唯一会话。即使传入显式 `store.db` / `meta.json`，也优先使用全局项目目录中同一会话 ID 的有序 transcript；`related_transcript_selected` 警告会给出实际选用路径。此流程需要获准读取关联数据，不能用于仅授权单个文件的场景；这类场景改用明确获准的 JSONL 导出。其他 store 中只恢复可解释的 JSON，二进制/protobuf 不解码。

列表按当前目录及时间筛选；不同版本的私有格式可能不兼容，空列表并不证明没有历史。原生 ID 与显式路径可能指向其他项目，必须核对来源与当前工作区。Cursor 的工作目录优先取自来源元数据；无工作目录的原始 JSONL 保持未知，不把当前 `--cwd` 冒充为来源目录。部分来源的自动发现会读取跨目录元数据以匹配当前项目；只在授权范围允许时使用。

reader 不承诺完整导出：工具结果是截断预览，压缩替换、未知类型、缺失引用以及不可解码内容可能造成缺口。数据库 blob 的键排序也不保证真实对话顺序。必要时报告无法确定停止点，不凭空补齐。
