import os

def append_to_file(path, content):
    with open(path, 'a', encoding='utf-8') as f:
        f.write("\n\n" + content + "\n")

memory_content = """## [Draft] 基于事实三元组的双通道长期记忆与异步预热 (Dual-Channel Memory & Async Warmup)
- **竞品来源**: Hermes Agent v0.16.0
- **借鉴的关键原文描述**: “热通道：上下文窗口 + 自动摘要压缩... 冷通道：长期记忆，采用语义双写 + 混合检索策略... 每次对话结束后台抽取结构化‘事实三元组’... 向量(HNSW)+BM25双路召回与倒数融合排序... 时效性衰减... 记忆检索改为非阻塞异步操作... 静默冲突解决策略（overwrite/ask_user）。”
- **借鉴的源代码位置标注**: 
  - 竞品参考: 外部项目/文章介绍
  - 我方应用位置: `app/database/models/memory.py` (如 `PendingMemory`) 和 `agent_repo.py` (`AgentMemoryPolicy`)。
- **原因与价值**: 当前我们在语义抽取、多路召回（HNSW+BM25结合倒数排序融合）、冲突解决方面偏弱，且同步检索拖慢首轮响应。加入这些特性，可以实现“过目不忘”的超强记忆及不卡顿的体验，构建完美的知识图谱。"""

multi_agent_content = """## [Draft] Supervisor 模式的图状协同与无序并发执行 (Supervisor DAG & Parallel Execution)
- **竞品来源**: Hermes Agent v0.16.0
- **借鉴的关键原文描述**: “推出 Supervisor 模式的图状拓扑... 包含 nodes（每个节点的 Agent、任务、依赖）和 edges... DAG 执行器识别无依赖关系的节点，通过 asyncio 并发执行... 实测 3 个工具调用总耗时从 4.0s 降至 2.0s，降幅 50%。”
- **借鉴的源代码位置标注**: 
  - 我方应用位置: `myrm_agent_harness/agent/sub_agents/orchestrator.py` 的 `execute_dag_plan` 和 工具调用流程。
- **原因与价值**: 将我们目前的链式或初步的并行执行，升级为彻底的拓扑分析与无序并发执行。这对复杂场景下的性能提升是压倒性的（>50%耗时缩减）。

## [Draft] 流式事件总线与流式思考-行动交织 (Stream Interleaving & Event Bus)
- **竞品来源**: Hermes Agent v0.16.0
- **借鉴的关键原文描述**: “流式网格事件总线实时推送所有事件... 在‘行动’阶段可同时‘思考’，基于当前信息预推演下一步方向。”
- **借鉴的源代码位置标注**: 
  - 我方应用位置: `app/api/agents/general_agent/streaming.py` 和 前端 Dashboard 订阅。
- **原因与价值**: 使用户可以在 WebUI/Tauri 实时可视化追踪“黑盒”里的子节点状态，且提升 LLM 工具调用的时间重叠率。"""

native_os_content = """## [Draft] 跨平台原生桌面自动化与四级定位引擎 (Native Desktop Automation Engine)
- **竞品来源**: Hermes Agent v0.16.0
- **借鉴的关键原文描述**: “跨平台底层实现... macOS 基于 Accessibility API... Windows 基于 UI Automation API... 四级元素定位引擎（AXIdentifier > 文本 > 控件 > 截图视觉兜底）... 三层安全沙箱（运行时首次弹窗确认、可回放）。”
- **借鉴的源代码位置标注**: 
  - 我方应用位置: `myrm-agent-desktop` (Tauri原生支持) 及 Python Server `command_center.py` 对本地环境的交互调用。
- **原因与价值**: 真正的管家必须有“双手”。通过四级引擎（特别是底层 API+视觉兜底），我们的桌面端不再受限于简单的命令，而是能像人一样全方位物理操控桌面。加入安全沙箱彻底解决高危权限的用户担忧。"""

general_content = """## [Draft] 极简化声明式配置 (Agentfile.yaml) 与社区克隆分享
- **竞品来源**: Hermes Agent v0.16.0
- **借鉴的关键原文描述**: “声明式 agentfile.yaml 配置文件，用 agentfile 即可完整定义 Agent 网格，无需编写 Python 代码... 社区 Agent 市场，非技术用户一键安装。”
- **借鉴的源代码位置标注**: 
  - 我方应用位置: Server 核心层配置加载逻辑，补充 `.myrm.yaml` 或 `agentfile.yaml` 格式。
- **原因与价值**: 从“写代码配代理”降维打击到“写YAML分享代理”。极大降低企业和普通用户的部署门槛，直接赋能未来的模板市场和插件生态。

## [Draft] 更稳定的解码校验与微虚拟机沙箱 (Structured Decoding & MicroVM Sandbox)
- **竞品来源**: Hermes Agent v0.16.0
- **借鉴的关键原文描述**: “沙盒化代码执行... 基于 Firecracker microVM 实现，启动约 125ms，内存约 5MB。默认无网络、硬限制、执行完快照回滚。结构化解码引擎... 收到响应后，状态机逐字段校验... 仅重试一次。”
- **借鉴的源代码位置标注**: 
  - 我方应用位置: Agent 代码执行工具链，以及 `general_agent/streaming.py` 输出校验阶段。
- **原因与价值**: 安全是底线，微虚拟机带来企业级的代码执行隔离。状态机级别的重试和格式校验，防崩溃。解决由于模型幻觉引发的无限递归重试（文中提到的坑）。"""

base_dir = "/Users/yululiu/projects/AI/open-perplexity/temp-docs/roadmap/"
append_to_file(os.path.join(base_dir, "HERMES_INSPIRED_AGENT_MEMORY_PERSONA_UX_ROADMAP.md"), memory_content)
append_to_file(os.path.join(base_dir, "MULTI_AGENT_ORCHESTRATION_AND_A2A_PROTOCOL_ROADMAP.md"), multi_agent_content)
append_to_file(os.path.join(base_dir, "NATIVE_OS_CONTROL_AND_GUI_AUTOMATION_ROADMAP.md"), native_os_content)
append_to_file(os.path.join(base_dir, "GENERAL_AI_ASSISTANT_EXPERIENCE_AND_AGENT_EVOLUTION_ROADMAP.md"), general_content)
print("Updated roadmaps successfully.")
