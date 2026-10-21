/**
 * 侧边独立解释分支与只读快照数据模型
 */

export interface ReadOnlyCodeSnapshot {
  filePath: string;
  codeSnippet: string;
  language: string;
  startLine?: number;
  endLine?: number;
  isDiff?: boolean;
}

export interface ReadOnlyStepSnapshot {
  stepId: string;
  stepTitle: string;
  toolAction?: string;
  outputSummary?: string;
  durationMs?: number;
}

export interface ForkedSessionSnapshot {
  mainSessionId: string;
  forkTimestamp: number;
  mainTaskName: string;
  activeStep?: ReadOnlyStepSnapshot;
  codeSnapshots: ReadOnlyCodeSnapshot[];
  branchName?: string;
  isUncommittedWorktree: boolean;
}

export interface SideTrackMessage {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  referencedSnippet?: ReadOnlyCodeSnapshot;
}

export interface SideTrackSession {
  sideSessionId: string;
  mainSessionId: string;
  title: string;
  status: 'idle' | 'generating';
  snapshot: ForkedSessionSnapshot;
  messages: SideTrackMessage[];
  presetInquiries: string[];
}
