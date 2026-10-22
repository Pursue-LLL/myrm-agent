export type StarMapNodeType = 'skill' | 'memory';

export type StarMapNodeScope = 'global' | 'agent-specific';

export interface RadialPosition {
  r: number;
  theta: number;
  x: number;
  y: number;
}

export interface StarMapNode {
  id: string;
  type: StarMapNodeType;
  name: string;
  summary: string;
  createdAt: number;
  recallCount: number;
  sourceChatId?: string;
  agentId?: string;
  scope: StarMapNodeScope;
  evolutionCount?: number;
  tags: string[];
  radialPosition?: RadialPosition;
}

export type StarMapLinkRelation = 'co-occurrence' | 'evolution' | 'chat-source';

export interface StarMapLink {
  id: string;
  sourceId: string;
  targetId: string;
  relation: StarMapLinkRelation;
  strength: number;
}

export interface TimeBucket {
  bucketIndex: number;
  startTime: number;
  endTime: number;
  label: string;
  skillCount: number;
  memoryCount: number;
}

export interface StarMapFilter {
  scope: 'all' | 'used' | 'learned';
  type: 'all' | 'skill' | 'memory';
  agentScope: 'all' | 'global' | 'agent-specific';
  timeSpan: 'all' | '90d' | '30d' | '7d';
  hideLabels: boolean;
}

export interface StarMapPlaybackState {
  isPlaying: boolean;
  currentProgress: number; // 0.0 to 1.0
  playbackSpeed: number; // 1x, 2x, 5x
  currentCutoffTimestamp: number;
}
