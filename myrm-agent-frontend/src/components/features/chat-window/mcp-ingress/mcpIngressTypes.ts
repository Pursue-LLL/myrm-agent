/**
 * [INPUT]
 * - None (纯类型与契约定义)
 *
 * [OUTPUT]
 * - McpProtocolType: MCP/Skill 链接协议类型
 * - McpSecurityLevel: 安全沙箱体检级别
 * - McpToolDescriptor: 暴露的工具元数据描述
 * - McpProbeResult: 即时探测握手结果
 * - McpMountMode: 三级装配模式
 * - McpMountStatus: 挂载生命周期状态
 * - McpMountPayload: 装配下发 Payload 契约
 *
 * [POS]
 * 会话流零摩擦 MCP 与技能链接智能嗅探、即时握手探测与一键热挂载卡片的核心类型定义。
 */

export type McpProtocolType = 'mcp-sse' | 'mcp-streamable' | 'github-skill' | 'openapi';

export type McpSecurityLevel = 'safe' | 'warning' | 'blocked';

export interface McpToolDescriptor {
  name: string;
  description: string;
  parameters?: Record<string, string>;
}

export interface McpProbeResult {
  url: string;
  serviceName: string;
  protocol: McpProtocolType;
  securityLevel: McpSecurityLevel;
  securityReason?: string;
  tools: McpToolDescriptor[];
  probeDurationMs: number;
  probedAt: number;
}

export type McpMountMode = 'session_ephemeral' | 'agent_persistent' | 'clone_new_agent';

export type McpMountStatus = 'idle' | 'probing' | 'probed' | 'mounting' | 'mounted' | 'error';

export interface McpMountPayload {
  url: string;
  probe: McpProbeResult;
  mountMode: McpMountMode;
  sessionId: string;
  agentId?: string;
}
