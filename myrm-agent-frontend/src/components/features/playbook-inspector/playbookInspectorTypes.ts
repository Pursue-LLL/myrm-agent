/**
 * [INPUT]
 * - None (纯契约与数据模型定义)
 *
 * [OUTPUT]
 * - PlaybookStatus: 规约生命周期状态枚举 ('active' | 'degraded' | 'retired')
 * - PlaybookFailureTrace: 规约失败追踪记录契约
 * - PlaybookRule: 判断力行为规约实体契约
 * - PlaybookFilter: 治理控制台过滤状态
 *
 * [POS]
 * 判断力规约生命周期可视化仪表盘、胜率追溯与人工修正复活工作台的核心契约类型。
 */

export type PlaybookStatus = 'active' | 'degraded' | 'retired';

export interface PlaybookFailureTrace {
  sessionId: string;
  timestamp: number;
  errorSummary: string;
  contextSnippet?: string;
}

export interface PlaybookRule {
  id: string;
  title: string;
  triggerCondition: string;
  directive: string;
  status: PlaybookStatus;
  triggerCount: number;
  successCount: number;
  winRate: number; // 0.0 ~ 1.0
  isPinned: boolean;
  recentFailures: PlaybookFailureTrace[];
  lastTriggeredAt: number;
  updatedAt: number;
}

export type PlaybookFilter = 'all' | 'active' | 'degraded' | 'retired' | 'pinned';
