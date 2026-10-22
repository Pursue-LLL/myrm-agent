/**
 * 豆包工作式结构化按需确认选项卡片与九大入口导航中枢类型定义
 */

export type OptionLetterId = 'A' | 'B' | 'C' | 'D' | 'E' | 'F';

export interface ConfirmationOptionItem {
  id: OptionLetterId;
  label: string;
  description?: string;
  isRecommended?: boolean;
  tag?: string;
}

export interface OnDemandDecisionInterrupt {
  interruptId: string;
  taskId: string;
  prompt: string;
  contextSummary?: string;
  options: ConfirmationOptionItem[];
  allowCustomInput?: boolean;
  placeholder?: string;
  timeoutSeconds?: number;
}

export interface ConfirmationDecisionResult {
  interruptId: string;
  taskId: string;
  selectedOptionId: OptionLetterId;
  selectedOptionLabel: string;
  customInput?: string;
  decidedAt: string;
}

export type NineEntryId =
  | 'new_task'
  | 'cron_jobs'
  | 'skills_mcp'
  | 'agents'
  | 'drive_projects'
  | 'mobile_pair'
  | 'main_chat'
  | 'kanban_roadmap'
  | 'recent_history';

export type EntryCategory = 'lifecycle' | 'collaboration' | 'assets';

export interface NineEntryNavItem {
  id: NineEntryId;
  label: string;
  description: string;
  shortcut: string;
  category: EntryCategory;
  badge?: string;
}
