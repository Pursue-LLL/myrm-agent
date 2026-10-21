export type RichSpanType =
  | 'plain'
  | 'bold'
  | 'italic'
  | 'inline_code'
  | 'ansi_color'
  | 'link';

export interface RichSpan {
  text: string;
  type: RichSpanType;
  colorClass?: string;
  url?: string;
}

export type StreamBlockType =
  | 'paragraph'
  | 'code_block'
  | 'tool_call'
  | 'terminal_ansi'
  | 'system_alert';

export interface TypedStreamBlock {
  id: string;
  type: StreamBlockType;
  language?: string;
  spans: RichSpan[];
  isFinalized: boolean;
  metadata?: Record<string, string | number | boolean>;
}

export type ViewportAnchorMode = 'PINNED_BOTTOM' | 'USER_DETACHED';

export interface ElasticSlotViewport {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
  anchorMode: ViewportAnchorMode;
  activeSlotIndex: number;
  totalSlotsCount: number;
}

export interface StreamPerformanceMetrics {
  parseDurationMs: number;
  tokenCount: number;
  throughputTokensPerSec: number;
  estimatedCpuUsagePct: number;
  memoryAllocatedBytes: number;
}
