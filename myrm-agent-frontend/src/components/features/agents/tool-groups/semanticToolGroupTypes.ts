/**
 * Semantic Tool Group Types
 * 权限能力语义组、零终端配置与细粒度安全策略类型定义
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any；
 * 2. 纯粹、具体、强类型约束；
 * 3. 行数严格受控。
 */

export type ToolGroupId = 'runtime' | 'filesystem' | 'memory' | 'web' | 'ui' | 'messaging';

export type SecurityPolicyLevel =
  | 'isolated_sandbox'
  | 'read_only'
  | 'requires_approval'
  | 'unrestricted';

export type SecurityRiskLevel = 'safe' | 'moderate' | 'high_risk';

export type SecurityPreset = 'strict_safe' | 'standard_assistant' | 'dev_expert' | 'custom';

export interface SemanticToolItem {
  id: string;
  name: string;
  description: string;
  risk: SecurityRiskLevel;
  isDefaultEnabled: boolean;
}

export interface SemanticToolGroupDefinition {
  id: ToolGroupId;
  title: string;
  categoryName: string;
  description: string;
  iconName: 'Terminal' | 'FolderGit2' | 'Brain' | 'Globe' | 'Layout' | 'Send';
  defaultSecurityLevel: SecurityPolicyLevel;
  supportedSecurityLevels: SecurityPolicyLevel[];
  tools: SemanticToolItem[];
}

export interface ToolGroupState {
  enabled: boolean;
  securityLevel: SecurityPolicyLevel;
  disabledToolIds: string[];
}

export interface AgentToolPolicyConfig {
  version: string;
  preset: SecurityPreset;
  groups: Record<ToolGroupId, ToolGroupState>;
  effectiveToolsCount: number;
  overallRisk: SecurityRiskLevel;
  riskScore: number; // 0 - 100 分，越高越安全
  generatedAt: string;
}

export interface CompiledToolExecutionPolicy {
  allowedTools: string[];
  deniedTools: string[];
  groupPolicies: Record<ToolGroupId, {
    enabled: boolean;
    level: SecurityPolicyLevel;
    activeToolCount: number;
  }>;
  elevationRequired: boolean;
  requiresConfirmationForExecution: boolean;
}
