/**
 * [INPUT]
 * - None (纯契约与数据模型定义)
 *
 * [OUTPUT]
 * - HandoffItemCategory: 交接条目类别枚举
 * - HandoffItem: 交接决策/待办/约束条目契约
 * - HandoffBrief: 跨会话预计算简报实体
 * - HandoffInjectPayload: 注入新会话上下文 Payload
 *
 * [POS]
 * 跨会话交接简报后台异步流式预生成与前端可编辑审阅抽屉的核心类型契约。
 */

export type HandoffItemCategory = 'decision' | 'todo' | 'constraint' | 'artifact';

export interface HandoffItem {
  id: string;
  category: HandoffItemCategory;
  content: string;
  enabled: boolean;
  isCustom?: boolean;
}

export interface HandoffBrief {
  sessionId: string;
  sessionTitle: string;
  summary: string;
  items: HandoffItem[];
  artifacts: string[];
  precomputedAt: number;
  precomputeDurationMs: number;
}

export interface HandoffInjectPayload {
  sourceSessionId: string;
  sourceSessionTitle: string;
  selectedItems: HandoffItem[];
  customNotes?: string;
  injectedPrompt: string;
}
