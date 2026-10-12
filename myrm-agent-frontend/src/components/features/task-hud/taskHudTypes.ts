/**
 * Type contracts for Anti-Compaction Task HUD & Session Task State.
 *
 * [INPUT] None
 * [OUTPUT] TaskStatus, TaskItem, SessionTaskHudData, TaskHudOverlayProps
 * [POS] Item 31 frontend type contracts. Strictly under 120 lines. Zero `any`.
 */

export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface TaskItem {
  id: string;
  title: string;
  status: TaskStatus;
  progress_percent: number;
  details?: string;
  created_at: string;
  updated_at: string;
}

export interface SessionTaskHudData {
  session_id: string;
  tasks: TaskItem[];
  overall_progress: number;
  active_task_id: string | null;
  hud_injection_text: string;
  updated_at: string;
}

export interface TaskHudOverlayProps {
  chatId?: string;
  className?: string;
}
