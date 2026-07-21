# assets 目录架构

MyrmAgent 产品资产（非框架代码）。官方预置技能种子，启动时由 `app/core/skills/prebuilt_sync.py` 同步到 workspace storage。

## 子目录

| 目录 | 职责 |
|------|------|
| `prebuilt_skills/` | 官方 SKILL.md 种子（deep-research、github-workflow、daily-briefing、google-workspace 等）。凡引用 `bash_code_execute_tool` 的 skill 含 **Bash execution contract**（`reason` ≥10 字 + `command`）。厂商 OAuth skill 在 frontmatter 声明 `oauth_issuer`（如 `google_workspace`），需配套 `app/api/integrations/` OAuth 流程；harness 按 skill 路径 scoped 注入 token |
| `prebuilt_agents/` | 预配置 Agent 模板 YAML。支持 individual（单体）和 team（多 Agent 协作团队）两种类型。team 模板定义 members + leader + use_cases，由 `app/api/agents/templates.py` 解析并原子实例化。 |
| `cookbook_specs.json` | Ollama Hardware Cookbook 模型规格（bundled；`model_specs.py` 加载；`tests/architecture/test_cookbook_specs_asset.py` 校验结构） |
