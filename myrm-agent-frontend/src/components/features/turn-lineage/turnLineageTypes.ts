export type TurnOriginType =
  | 'user_direct'
  | 'cron_job'
  | 'webhook_trigger'
  | 'subagent_delegation'
  | 'approval_resume';

export interface TurnProvenanceMeta {
  originType: TurnOriginType;
  originRefId: string;
  triggerSourceTitle: string;
  executedByAgent: string;
  timestamp: string;
  causalityParentId?: string;
  details?: Record<string, string>;
}

export interface ChatTurnItem {
  id: string;
  turnNumber: number;
  role: 'user' | 'assistant' | 'system';
  author: string;
  content: string;
  provenance: TurnProvenanceMeta;
  tokensUsed: number;
  durationMs: number;
}

export type LineageFilterMode =
  | 'all'
  | 'user_only'
  | 'automated_only'
  | 'handoff_only';

export interface OriginVisualTheme {
  label: string;
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
  dotColor: string;
  description: string;
}
