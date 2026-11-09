/**
 * [INPUT]
 * @/store/chat/types::{Message,McpAppView,ProgressItem,ToolImageOutput} (POS: Chat message model and its attachment views)
 * ../CronJobSystemCard::CronJobResult (POS: Scheduled-job result shown by the cron system card)
 * ../KanbanTaskCreatedCard::KanbanTaskCreatedResult (POS: Created-task result shown by the kanban card)
 *
 * [OUTPUT]
 * closeUnbalancedReasoningTags / parseAsyncTaskResponse / parseTtsAudioResponse / readSessionRecording /
 * readToolImages / readMcpApps / readCronJobResult / readKanbanTasksCreated / resolveProgressSteps:
 * Typed readers that turn the loosely typed payload of one assistant message into what its cards render.
 *
 * [POS]
 * Pure readers for assistant message payloads. Persisted and streamed messages can carry malformed values, so every
 * reader validates what it returns and falls back to an empty result instead of throwing.
 */

import type { McpAppView, Message, ProgressItem, ToolImageOutput } from '@/store/chat/types';
import type { CronJobResult } from '../CronJobSystemCard';
import type { KanbanTaskCreatedResult } from '../KanbanTaskCreatedCard';

/** Reply of an async generation tool: the answer is a task card, not text. */
export type AsyncTaskResponse = { task_id: string; task_type?: string; status?: string; message?: string };

/** Successful reply of the text-to-speech tool: the answer is an audio player, not text. */
export type TtsAudioResponse = { audio_url: string; model?: string; duration_seconds?: number };

const REASONING_TAGS = ['think', 'thinking', 'thought', 'antthinking', 'reasoning', 'REASONING_SCRATCHPAD'] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseJsonObject(content: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(content);
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** Closes every reasoning block the stream is still inside, so the renderer always receives complete blocks. */
export function closeUnbalancedReasoningTags(content: string): string {
  if (!content) {
    return '';
  }
  if (!content.includes('<')) {
    return content;
  }
  let closed = content;
  for (const tag of REASONING_TAGS) {
    const opened = closed.match(new RegExp(`<${tag}>`, 'gi'))?.length ?? 0;
    const closes = closed.match(new RegExp(`</${tag}>`, 'gi'))?.length ?? 0;
    if (opened > closes) {
      closed += `</${tag}> <a> </a>`;
    }
  }
  return closed;
}

export function parseAsyncTaskResponse(content: string): AsyncTaskResponse | null {
  const parsed = parseJsonObject(content);
  return parsed && typeof parsed.task_id === 'string' && parsed.task_id ? (parsed as AsyncTaskResponse) : null;
}

export function parseTtsAudioResponse(content: string): TtsAudioResponse | null {
  const parsed = parseJsonObject(content);
  return parsed && parsed.status === 'success' && typeof parsed.audio_url === 'string'
    ? (parsed as TtsAudioResponse)
    : null;
}

export function readSessionRecording(message: Message): { filename: string; preview_url: string } | null {
  const recording = message.sessionRecording;
  return isRecord(recording) && typeof recording.filename === 'string' && typeof recording.preview_url === 'string'
    ? recording
    : null;
}

export function readToolImages(message: Message): ToolImageOutput[] {
  return Array.isArray(message.toolImages) ? message.toolImages : [];
}

export function readMcpApps(message: Message): McpAppView[] {
  return Array.isArray(message.mcpApps) ? message.mcpApps : [];
}

export function readCronJobResult(message: Message): CronJobResult | null {
  const result = isRecord(message.metadata) ? message.metadata.cron_job_result : undefined;
  return result ? (result as CronJobResult) : null;
}

function isKanbanTaskCreated(item: unknown): item is KanbanTaskCreatedResult {
  return (
    isRecord(item) &&
    typeof item.task_id === 'string' &&
    typeof item.title === 'string' &&
    typeof item.board_id === 'string'
  );
}

export function readKanbanTasksCreated(message: Message): KanbanTaskCreatedResult[] {
  const raw = isRecord(message.metadata) ? message.metadata.kanban_tasks_created : undefined;
  return Array.isArray(raw) ? raw.filter(isKanbanTaskCreated) : [];
}

/** The steps shown for a message: `progressSteps`, or the copy in `metadata.progressSteps` when that is empty. */
export function resolveProgressSteps(message: Message): ProgressItem[] {
  if (message.progressSteps?.length) {
    return message.progressSteps;
  }
  const persisted = message.metadata?.progressSteps;
  return Array.isArray(persisted) ? (persisted as ProgressItem[]) : [];
}
