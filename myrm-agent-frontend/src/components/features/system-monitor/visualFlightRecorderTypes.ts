/**
 * [INPUT]: Visual frames, failure slices, and modal playback state parameters.
 * [OUTPUT]: Strong TypeScript definitions for VisualFailureFlightRecorderModal component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/visualFlightRecorderTypes.ts
 */

export type VisualFailureKind =
  | 'popup_overlay'
  | 'captcha_slider'
  | 'element_timeout'
  | 'stuck_loop'
  | 'browser_crash'
  | string;

export interface VisualFrameItem {
  frame_index: intOrNumber;
  timestamp_ms: number;
  image_data_uri: string;
  width?: number;
  height?: number;
  dom_event_summary?: string;
}

type intOrNumber = number;

export interface VisualFailureSliceItem {
  slice_id: string;
  trace_id: string;
  session_id: string;
  failure_kind: VisualFailureKind;
  root_cause_label: string;
  total_frames: number;
  duration_seconds: number;
  frames: VisualFrameItem[];
  animated_preview_uri?: string;
  created_at_ms: number;
}

export interface VisualFailureFlightRecorderModalProps {
  isOpen: boolean;
  onClose: () => void;
  slices: VisualFailureSliceItem[];
  selectedSliceId?: string;
  onSelectSlice?: (sliceId: string) => void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}
