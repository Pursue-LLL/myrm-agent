/**
 * [INPUT]: Decoupled multimodal media references, 3-step inspection stages, and Golden Eval data.
 * [OUTPUT]: Strong TypeScript definitions for MultimodalTraceViewerModal component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/multimodalTraceTypes.ts
 */

export type MediaModalityType = 'image' | 'audio' | 'video' | 'document';

export type MediaVisibilityStateType = 'ready' | 'uploading' | 'expired' | 'purged';

export type MultimodalStepKind = 'input' | 'execution' | 'feedback';

export interface MediaReferenceItem {
  media_id: string;
  uri: string;
  modality: MediaModalityType;
  mime_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  visibility_state: MediaVisibilityStateType;
  presigned_preview_url: string;
  created_at_ms: number;
}

export interface MultimodalTraceStepItem {
  step_index: number;
  step_type: MultimodalStepKind;
  description: string;
  media_ids: string[];
  status: string;
  timestamp_ms: number;
}

export interface MultimodalTraceRecordItem {
  trace_id: string;
  session_id: string;
  prompt_summary: string;
  media_references: MediaReferenceItem[];
  steps: MultimodalTraceStepItem[];
  pinned_for_golden_eval: boolean;
  golden_eval_category: string;
  created_at_ms: number;
}

export interface MultimodalTraceViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  traces: MultimodalTraceRecordItem[];
  selectedTraceId?: string;
  onSelectTrace?: (traceId: string) => void;
  onPinGoldenEval?: (traceId: string, category: string) => Promise<void> | void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}
