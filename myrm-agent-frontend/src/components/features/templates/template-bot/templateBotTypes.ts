/**
 * TemplateBot Marketplace & P0 Urgency Cruise Control Types
 * 预制岗位智能体模板市场、一键克隆团队与 P0 紧急高频纠偏巡航状态机定义
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 字段完备语义化。
 */

export type TemplateRoleCategory =
  | 'management'
  | 'engineering'
  | 'research'
  | 'finance'
  | 'operations';

export interface TemplateBotRole {
  id: string;
  name: string;
  category: TemplateRoleCategory;
  department: string;
  avatarBadge: string;
  summary: string;
  defaultSystemPrompt: string;
  recommendedSkillIds: string[];
  defaultTools: string[];
  maxContextTokens: number;
  author: string;
  starsCount: number;
}

export interface TeamRosterTemplate {
  teamId: string;
  teamName: string;
  description: string;
  category: TemplateRoleCategory;
  roles: TemplateBotRole[];
  collaborationTopology: 'hierarchical' | 'peer_swarm' | 'pipeline';
  estimatedTokenBudgetMultiplier: number;
}

export interface P0WatchdogLogEntry {
  id: string;
  timestamp: number;
  inspectionRound: number;
  status: 'passed' | 'warning' | 'steered';
  detectedIssue?: string;
  injectedSteeringPrompt?: string;
}

export interface P0UrgencyCruiseState {
  isActive: boolean;
  taskId: string | null;
  taskTitle: string;
  urgencyLevel: 'normal' | 'p0_urgent';
  inspectionIntervalSeconds: number;
  lastInspectionTimestamp: number;
  nextInspectionCountdownSeconds: number;
  deviationInterceptCount: number;
  steeringInjectedCount: number;
  watchdogLogs: P0WatchdogLogEntry[];
}

export interface TeamCloneResult {
  teamId: string;
  instantiatedBotIds: string[];
  createdAtTimestamp: number;
  status: 'instantiated' | 'failed';
}
