/**
 * [INPUT]
 * @/store/chat/types::Message (POS: Chat message domain types)
 * ../adaptiveScheduler::AdaptiveScheduler (POS: Streaming UI update scheduler)
 *
 * [OUTPUT]
 * StreamHandlerState, StreamHandlerActions, StreamMutableState: contracts for SSE reducer
 *
 * [POS]
 * Type definitions for the chat message stream handler subsystem.
 */

import type { Message } from '@/store/chat/types';
import type { AdaptiveScheduler } from '../adaptiveScheduler';

export interface StreamMutableState {
  messages: Message[];
  messageAppeared: boolean;
  loading: boolean;
}

export interface StreamHandlerState extends StreamMutableState {
  scheduler: AdaptiveScheduler;
}

export interface StreamHandlerActions {
  setMessages: (updater: (state: StreamMutableState) => void) => void;
  setMessageAppeared: (appeared: boolean) => void;
  setLoading: (loading: boolean) => void;
  _processSuggestions: (lastMsg: Message) => Promise<void>;
  scheduleAutoSave: () => void;
}

/** progressSteps file row mutated when merging FILE_DIFF */
export type ProgressFileItem = {
  file_path: string;
  line_range?: string;
  action_type?: string;
  size_bytes?: string;
  diff?: string;
  diff_truncated?: boolean;
};
