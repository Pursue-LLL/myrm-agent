export type VisibilityScope = 'human_visible' | 'hidden_bot_peer';

export type BotActivityStatus = 'in_progress' | 'completed' | 'failed';

export interface BotActivityItem {
  id: string;
  sessionId: string;
  sourceAgent: string;
  targetAgent: string;
  actionSummary: string;
  payloadSnippet: string;
  tokenCost: number;
  latencyMs: number;
  timestamp: number;
  status: BotActivityStatus;
}

export interface AmbientDeckSummary {
  activeAgentsCount: number;
  totalExchangesCount: number;
  totalTokenCost: number;
  recentHighlights: string[];
}

export interface ConversationWithVisibility {
  id: string;
  title: string;
  visibilityScope?: VisibilityScope;
  updatedAt?: number;
}
