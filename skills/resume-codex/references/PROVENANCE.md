# 来源与许可状态

本 Skill 改编自用户提供的 Grok Build bundled skills 导出包，包内 README 标识缓存版本 `public-2026-10-09-r1`；未独立验证该版本标签。

上游资源：`resume-claude/SKILL.md`、`resume-codex/SKILL.md`、`resume-cursor/SKILL.md`，以及 `shared/resume-session/CORE.md` 和 `session_reader.py`。

用户提供的原始 reader SHA-256：`342853ca19f8d9f10dd171890ee1bbacec2350ea90221cb4ad6925cda2380a58`。

改动：三个入口各自携带 core 和 reader；移除特定执行宿主、隐含运行时变量及兄弟目录依赖；文档改为中文并明确访问与续做边界。reader 的后续修订以仓库 diff 为准。

所提供的包未包含上游 LICENSE 或明确的再分发许可。本文件只记录出处，不授予上游代码许可，也不将其声明为 Apache-2.0、MIT 或本仓库的其他许可。公开再分发前须由维护者确认相应权利。
