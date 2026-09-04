# Continual Session Overlay Service

[INPUT]
- `myrm_agent_harness.agent.session_overlay.schema::SessionOverlay`: 现场自愈外壳契约模型
- `app.services.skills.draft_notification::persist_skill_draft_record`: 技能成长持久化入口

[OUTPUT]
- `graduate_session_overlay_to_growth`: 将经过验证的有效自愈外壳毕业晋级为可人工审核的技能成长案例

[POS]
连接底层 Agent Harness 现场自愈外壳与服务端技能进化（Skill Growth）资产化审批流的业务桥梁服务。

## 模块架构与职责

1. **业务桥梁解耦**：底层 Harness 保持通用单机纯净度，业务层通过该服务监听并接收成功自愈的外壳资产。
2. **渐进式资产化**：将临时会话态的参数剥离与负例规避，沉淀为永久性的技能成长草案。
