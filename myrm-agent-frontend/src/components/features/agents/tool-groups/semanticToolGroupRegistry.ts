/**
 * Semantic Tool Group Registry & Security Engine
 * 6 大业务语义组注册表、安全预设模板与策略编译计算引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全类型化；
 * 2. 所有 if 必须包裹大括号；
 * 3. 行数严格控制在 400 行以内。
 */

import {
  AgentToolPolicyConfig,
  CompiledToolExecutionPolicy,
  SecurityPolicyLevel,
  SecurityPreset,
  SecurityRiskLevel,
  SemanticToolGroupDefinition,
  ToolGroupId,
  ToolGroupState,
} from './semanticToolGroupTypes';

export const SEMANTIC_TOOL_GROUPS: SemanticToolGroupDefinition[] = [
  {
    id: 'runtime',
    title: '沙箱代码执行 (Runtime)',
    categoryName: '代码与命令',
    description: '提供隔离环境内命令行执行、解释器运行与进程调度能力',
    iconName: 'Terminal',
    defaultSecurityLevel: 'isolated_sandbox',
    supportedSecurityLevels: ['isolated_sandbox', 'requires_approval', 'unrestricted'],
    tools: [
      {
        id: 'runtime_exec_command',
        name: 'exec_command',
        description: '在安全容器或沙箱中执行单次 Shell 命令',
        risk: 'moderate',
        isDefaultEnabled: true,
      },
      {
        id: 'runtime_python_interpreter',
        name: 'python_interpreter',
        description: '在隔离子进程中计算并返回 Python 数据分析代码',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'runtime_bash_session',
        name: 'bash_session',
        description: '开启常驻交互式伪终端会话（高特权）',
        risk: 'high_risk',
        isDefaultEnabled: false,
      },
      {
        id: 'runtime_kill_process',
        name: 'kill_process',
        description: '强制终止超时或失控的运行期子进程',
        risk: 'moderate',
        isDefaultEnabled: true,
      },
    ],
  },
  {
    id: 'filesystem',
    title: '本地工作区读写 (Filesystem)',
    categoryName: '存储与文件',
    description: '允许智能体读取分析工作目录代码、修改文件与持久化产出',
    iconName: 'FolderGit2',
    defaultSecurityLevel: 'read_only',
    supportedSecurityLevels: ['read_only', 'requires_approval', 'unrestricted'],
    tools: [
      {
        id: 'fs_read_file',
        name: 'read_file',
        description: '读取工作区内的代码或配置文件内容',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'fs_list_directory',
        name: 'list_directory',
        description: '递归遍历工作空间目录结构与文件属性',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'fs_write_file',
        name: 'write_file',
        description: '向磁盘创建或覆盖新文件内容',
        risk: 'moderate',
        isDefaultEnabled: false,
      },
      {
        id: 'fs_replace_file_content',
        name: 'replace_file_content',
        description: '基于精准文本块或 AST 替换现有源码文件',
        risk: 'high_risk',
        isDefaultEnabled: false,
      },
    ],
  },
  {
    id: 'memory',
    title: '长效记忆沉淀 (Memory)',
    categoryName: '上下文与认知',
    description: '管理智能体跨会话长期事实记忆库与用户偏好资产',
    iconName: 'Brain',
    defaultSecurityLevel: 'requires_approval',
    supportedSecurityLevels: ['read_only', 'requires_approval', 'unrestricted'],
    tools: [
      {
        id: 'memory_store_fact',
        name: 'store_fact',
        description: '将本次会话的关键结论或用户偏好写入长期向量库',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'memory_recall_context',
        name: 'recall_context',
        description: '根据当前话题语义召回历史沉淀的上下文信息',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'memory_delete_profile',
        name: 'delete_profile',
        description: '重置或物理抹除特定实体的长期记忆档案',
        risk: 'high_risk',
        isDefaultEnabled: false,
      },
    ],
  },
  {
    id: 'web',
    title: '全网知识检索 (Web)',
    categoryName: '网络与爬虫',
    description: '赋予智能体实时互联网信息抓取、搜索与网页交互能力',
    iconName: 'Globe',
    defaultSecurityLevel: 'isolated_sandbox',
    supportedSecurityLevels: ['isolated_sandbox', 'requires_approval', 'unrestricted'],
    tools: [
      {
        id: 'web_search_engine',
        name: 'search_web',
        description: '向权威公网搜索引擎查询最新行业资料与实时资讯',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'web_fetch_url_content',
        name: 'fetch_url_content',
        description: '抓取指定公开网页并将 HTML 转换为 Markdown 文本',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'web_browser_headless_action',
        name: 'browser_action',
        description: '驱动无头浏览器执行点击、表单填写与截图交互',
        risk: 'high_risk',
        isDefaultEnabled: false,
      },
    ],
  },
  {
    id: 'ui',
    title: '界面交互卡片 (UI & Canvas)',
    categoryName: '界面与反馈',
    description: '生成即时可交互卡片、审批表单与图形画布控件',
    iconName: 'Layout',
    defaultSecurityLevel: 'unrestricted',
    supportedSecurityLevels: ['read_only', 'unrestricted'],
    tools: [
      {
        id: 'ui_render_interactive_card',
        name: 'render_card',
        description: '在消息流中动态呈现 GenUI 结构化交互卡片',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'ui_ask_user_choice',
        name: 'ask_user_choice',
        description: '弹出选项模态框向用户索取确定性决策分支',
        risk: 'safe',
        isDefaultEnabled: true,
      },
      {
        id: 'ui_canvas_paint_diagram',
        name: 'paint_diagram',
        description: '在侧边看板中渲染架构流图与序列状态机',
        risk: 'safe',
        isDefaultEnabled: true,
      },
    ],
  },
  {
    id: 'messaging',
    title: '外部通信网关 (Messaging)',
    categoryName: '集成与分发',
    description: '调度群聊频道通知、Webhook 回调与多智能体子派发',
    iconName: 'Send',
    defaultSecurityLevel: 'requires_approval',
    supportedSecurityLevels: ['requires_approval', 'unrestricted'],
    tools: [
      {
        id: 'msg_send_channel_alert',
        name: 'send_channel_alert',
        description: '向绑定钉钉/飞书/Slack 频道投递任务结项摘要',
        risk: 'moderate',
        isDefaultEnabled: false,
      },
      {
        id: 'msg_invoke_peer_agent',
        name: 'invoke_peer_agent',
        description: '唤醒并指派任务给同一集群下的子智能体伙伴',
        risk: 'moderate',
        isDefaultEnabled: true,
      },
      {
        id: 'msg_webhook_post',
        name: 'webhook_post',
        description: '向第三方外部系统投递自定义 JSON Webhook 载荷',
        risk: 'high_risk',
        isDefaultEnabled: false,
      },
    ],
  },
];

export const PRESET_CONFIGS: Record<Exclude<SecurityPreset, 'custom'>, Record<ToolGroupId, ToolGroupState>> = {
  strict_safe: {
    runtime: { enabled: false, securityLevel: 'isolated_sandbox', disabledToolIds: ['runtime_bash_session', 'runtime_exec_command', 'runtime_kill_process'] },
    filesystem: { enabled: true, securityLevel: 'read_only', disabledToolIds: ['fs_write_file', 'fs_replace_file_content'] },
    memory: { enabled: true, securityLevel: 'read_only', disabledToolIds: ['memory_delete_profile'] },
    web: { enabled: true, securityLevel: 'isolated_sandbox', disabledToolIds: ['web_browser_headless_action'] },
    ui: { enabled: true, securityLevel: 'read_only', disabledToolIds: [] },
    messaging: { enabled: false, securityLevel: 'requires_approval', disabledToolIds: ['msg_send_channel_alert', 'msg_invoke_peer_agent', 'msg_webhook_post'] },
  },
  standard_assistant: {
    runtime: { enabled: true, securityLevel: 'isolated_sandbox', disabledToolIds: ['runtime_bash_session'] },
    filesystem: { enabled: true, securityLevel: 'read_only', disabledToolIds: ['fs_replace_file_content'] },
    memory: { enabled: true, securityLevel: 'requires_approval', disabledToolIds: ['memory_delete_profile'] },
    web: { enabled: true, securityLevel: 'isolated_sandbox', disabledToolIds: ['web_browser_headless_action'] },
    ui: { enabled: true, securityLevel: 'unrestricted', disabledToolIds: [] },
    messaging: { enabled: true, securityLevel: 'requires_approval', disabledToolIds: ['msg_webhook_post'] },
  },
  dev_expert: {
    runtime: { enabled: true, securityLevel: 'requires_approval', disabledToolIds: [] },
    filesystem: { enabled: true, securityLevel: 'requires_approval', disabledToolIds: [] },
    memory: { enabled: true, securityLevel: 'unrestricted', disabledToolIds: [] },
    web: { enabled: true, securityLevel: 'unrestricted', disabledToolIds: [] },
    ui: { enabled: true, securityLevel: 'unrestricted', disabledToolIds: [] },
    messaging: { enabled: true, securityLevel: 'requires_approval', disabledToolIds: [] },
  },
};

export function calculateSecurityMetrics(groups: Record<ToolGroupId, ToolGroupState>): {
  riskScore: number;
  overallRisk: SecurityRiskLevel;
  effectiveToolsCount: number;
} {
  let riskPenalty = 0;
  let activeTools = 0;

  for (const group of SEMANTIC_TOOL_GROUPS) {
    const state = groups[group.id];
    if (!state || !state.enabled) {
      continue;
    }

    if (state.securityLevel === 'unrestricted') {
      riskPenalty += 20;
    } else if (state.securityLevel === 'requires_approval') {
      riskPenalty += 8;
    } else if (state.securityLevel === 'isolated_sandbox') {
      riskPenalty += 4;
    }

    for (const tool of group.tools) {
      if (!state.disabledToolIds.includes(tool.id)) {
        activeTools += 1;
        if (tool.risk === 'high_risk') {
          riskPenalty += 12;
        } else if (tool.risk === 'moderate') {
          riskPenalty += 5;
        }
      }
    }
  }

  const riskScore = Math.max(0, Math.min(100, 100 - riskPenalty));
  let overallRisk: SecurityRiskLevel = 'safe';
  if (riskScore < 50) {
    overallRisk = 'high_risk';
  } else if (riskScore < 75) {
    overallRisk = 'moderate';
  }

  return { riskScore, overallRisk, effectiveToolsCount: activeTools };
}

export function compileToolExecutionPolicy(
  groups: Record<ToolGroupId, ToolGroupState>
): CompiledToolExecutionPolicy {
  const allowedTools: string[] = [];
  const deniedTools: string[] = [];
  let elevationRequired = false;
  let requiresConfirmation = false;

  const groupPolicies: CompiledToolExecutionPolicy['groupPolicies'] = {} as CompiledToolExecutionPolicy['groupPolicies'];

  for (const group of SEMANTIC_TOOL_GROUPS) {
    const state = groups[group.id];
    let activeToolCount = 0;

    if (!state || !state.enabled) {
      for (const tool of group.tools) {
        deniedTools.push(tool.name);
      }
      groupPolicies[group.id] = {
        enabled: false,
        level: state ? state.securityLevel : group.defaultSecurityLevel,
        activeToolCount: 0,
      };
      continue;
    }

    if (state.securityLevel === 'unrestricted') {
      elevationRequired = true;
    }
    if (state.securityLevel === 'requires_approval') {
      requiresConfirmation = true;
    }

    for (const tool of group.tools) {
      if (state.disabledToolIds.includes(tool.id)) {
        deniedTools.push(tool.name);
      } else {
        allowedTools.push(tool.name);
        activeToolCount += 1;
        if (tool.risk === 'high_risk') {
          requiresConfirmation = true;
        }
      }
    }

    groupPolicies[group.id] = {
      enabled: true,
      level: state.securityLevel,
      activeToolCount,
    };
  }

  return {
    allowedTools,
    deniedTools,
    groupPolicies,
    elevationRequired,
    requiresConfirmationForExecution: requiresConfirmation,
  };
}

export function buildCompleteConfig(
  preset: SecurityPreset,
  groups: Record<ToolGroupId, ToolGroupState>
): AgentToolPolicyConfig {
  const metrics = calculateSecurityMetrics(groups);
  return {
    version: '2.0.0',
    preset,
    groups,
    effectiveToolsCount: metrics.effectiveToolsCount,
    overallRisk: metrics.overallRisk,
    riskScore: metrics.riskScore,
    generatedAt: new Date().toISOString(),
  };
}
