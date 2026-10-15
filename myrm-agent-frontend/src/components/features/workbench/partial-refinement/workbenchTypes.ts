export type WorkbenchResourceType =
  | 'document'
  | 'browser'
  | 'terminal'
  | 'code'
  | 'table';

export interface WorkbenchTab {
  id: string;
  title: string;
  type: WorkbenchResourceType;
  content: string;
  isModified?: boolean;
  metadata?: Record<string, string>;
}

export interface SelectionRange {
  startOffset: number;
  endOffset: number;
  selectedText: string;
  contextBefore: string;
  contextAfter: string;
}

export type RefinementStatus =
  | 'idle'
  | 'selecting'
  | 'prompting'
  | 'refining'
  | 'previewing'
  | 'applied'
  | 'rejected';

export interface ChunkRefinementTask {
  id: string;
  tabId: string;
  range: SelectionRange;
  userInstruction: string;
  originalChunk: string;
  refinedChunk: string;
  tokenSavingsPercent: number;
  latencyMs: number;
  createdAt: number;
}

export interface TokenSavingsStats {
  totalRefinements: number;
  totalTokensSaved: number;
  avgLatencyMs: number;
}
