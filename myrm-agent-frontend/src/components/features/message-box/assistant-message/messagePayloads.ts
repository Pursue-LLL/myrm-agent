/**
 * [INPUT]
 * @/store/chat/types::{Message,McpAppView,ProgressItem,ToolImageOutput} (POS: Chat message model and its attachment views)
 * @/lib/chat/mediaGenerated (POS: Media a media tool call registers from its structured result)
 * ../CronJobSystemCard::CronJobResult (POS: Scheduled-job result shown by the cron system card)
 * ../KanbanTaskCreatedCard::KanbanTaskCreatedResult (POS: Created-task result shown by the kanban card)
 *
 * [OUTPUT]
 * closeUnbalancedReasoningTags / readSessionRecording / readToolImages / readMcpApps / readCronJobResult /
 * readKanbanTasksCreated / readMediaGenerated / resolveProgressSteps:
 * Typed readers that turn the loosely typed payload of one assistant message into what its cards render.
 *
 * [POS]
 * Pure readers for assistant message payloads. Persisted and streamed messages can carry malformed values, so every
 * reader validates what it returns and falls back to an empty result instead of throwing.
 */

import {
  MEDIA_GENERATED_METADATA_KEY,
  readMediaGeneratedEntries,
  type MediaGeneratedEntry,
} from '@/lib/chat/mediaGenerated';
import type { McpAppView, Message, ProgressItem, ToolImageOutput } from '@/store/chat/types';
import type { CronJobResult } from '../CronJobSystemCard';
import type { KanbanTaskCreatedResult } from '../KanbanTaskCreatedCard';

const REASONING_TAGS = ['think', 'thinking', 'thought', 'antthinking', 'reasoning', 'REASONING_SCRATCHPAD'] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
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

/** The images, videos and audio the message's media tools produced, in the order they were produced. */
export function readMediaGenerated(message: Message): MediaGeneratedEntry[] {
  return readMediaGeneratedEntries(
    isRecord(message.metadata) ? message.metadata[MEDIA_GENERATED_METADATA_KEY] : undefined,
  );
}

/** The steps shown for a message: `progressSteps`, or the copy in `metadata.progressSteps` when that is empty. */
export function resolveProgressSteps(message: Message): ProgressItem[] {
  if (message.progressSteps?.length) {
    return message.progressSteps;
  }
  const persisted = message.metadata?.progressSteps;
  return Array.isArray(persisted) ? (persisted as ProgressItem[]) : [];
}
