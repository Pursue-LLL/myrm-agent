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
  /**
   * chatId of the chat owning this stream, captured at send time. For a brand-new
   * chat the message list may still be empty when the first turn streams, so
   * handlers must resolve the stream chatId from this field instead of
   * messages[0].chatId (which would be empty and silently no-op releases).
   */
  chatId?: string;
}

export interface StreamHandlerActions {
  setMessages: (updater: (state: StreamMutableState) => void) => void;
  setMessageAppeared: (appeared: boolean) => void;
  setLoading: (loading: boolean) => void;
  /** Mark a terminal SSE event as no longer streaming in the owning chat/pane. */
  clearActiveStream?: () => void;
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
