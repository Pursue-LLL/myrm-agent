/**
 * Session-scoped recurring loop API service.
 *
 * [INPUT]
 * @/lib/api::apiRequest
 *
 * [OUTPUT]
 * - SessionLoopStatus interface
 * - startSessionLoop, stopSessionLoop, getSessionLoopStatus
 *
 * [POS]
 * Client HTTP boundary for /loop session scheduling.
 */

import { apiRequest } from '@/lib/api';

export interface SessionLoopStatus {
  chat_id: string;
  is_active: boolean;
  status: 'active' | 'paused' | 'completed' | 'stopped' | 'cleared' | 'none';
  mode: 'interval' | 'self_paced';
  prompt: string;
  current_delay_seconds: number;
  current_delay_human: string;
  next_due_in_seconds: number;
  next_due_in_human: string;
  ticks_fired: number;
  times_limit: number;
  until_condition: string;
  consecutive_unchanged: number;
  last_stop_reason: string | null;
  paused_reason: string | null;
}

export const startSessionLoop = async (chatId: string, command: string): Promise<SessionLoopStatus> => {
  return apiRequest<SessionLoopStatus>(`/chats/${chatId}/loop/start`, {
    method: 'POST',
    body: JSON.stringify({ command }),
  });
};

export const stopSessionLoop = async (chatId: string, reason: string = 'user_stopped'): Promise<SessionLoopStatus> => {
  return apiRequest<SessionLoopStatus>(`/chats/${chatId}/loop/stop`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
};

export const getSessionLoopStatus = async (chatId: string): Promise<SessionLoopStatus> => {
  return apiRequest<SessionLoopStatus>(`/chats/${chatId}/loop/status`);
};
