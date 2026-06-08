# assets 目录架构

MyrmAgent 产品资产（非框架代码）。官方预置技能种子，启动时由 `app/core/skills/prebuilt_sync.py` 同步到 workspace storage。

## 子目录

| 目录 | 职责 |
|------|------|
| `prebuilt_skills/` | 官方 SKILL.md 种子（deep-research、github-workflow 等） |
| `prebuilt_agents/` | 预配置 Agent 模板 YAML。支持 individual（单体）和 team（多 Agent 协作团队）两种类型。team 模板定义 members + leader + use_cases，由 `app/api/agents/templates.py` 解析并原子实例化。 |
| `cookbook_specs.json` | Ollama Hardware Cookbook 模型规格（bundled；可选 `MYRM_MODEL_SPECS_REMOTE_URL` 覆盖）。**CDN 镜像**：`myrm-agent-brand/myrm-website/public/cookbook_specs.json`（本地 monorepo 须与 bundled 字节一致；`tests/architecture/test_cookbook_specs_asset.py` 校验） |
