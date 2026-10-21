/**
 * [INPUT]
 * @/store/chat/types::Message, ToolEndStreamEvent (POS: chat domain / SSE types)
 * ../skillManageBatchLink::linkSkillManageBatch (POS: skill_manage Undo batch linking)
 * ./handlerDeps (POS: memory citation helpers)
 *
 * [OUTPUT]
 * applyToolEndToMessage: folds a finished tool call into the assistant message that owns it
 *
 * [POS]
 * TOOL_END reducer body of toolLifecycleEvents. `message` is the draft handed out by `actions.setMessages`,
 * never a message read from the stream's start-of-turn snapshot (which cannot contain the running turn).
 */

import type { Message, ToolEndStreamEvent } from '@/store/chat/types';
import { linkSkillManageBatch } from '../skillManageBatchLink';
import * as H from './handlerDeps';

/** kanban_add_task reports a refused task as a successful call whose result carries `error`. */
function readKanbanSoftError(result: unknown): string | undefined {
  try {
    const resultObj = typeof result === 'string' ? JSON.parse(result) : result;
    if (resultObj && typeof resultObj === 'object' && typeof (resultObj as { error?: unknown }).error === 'string') {
      return (resultObj as { error: string }).error.trim() || undefined;
    }
  } catch {
    // parse failure is expected for non-kanban results
  }
  return undefined;
}

function readJsonObject(result: unknown): Record<string, unknown> | undefined {
  try {
    const resultObj = typeof result === 'string' ? JSON.parse(result) : result;
    return resultObj && typeof resultObj === 'object' ? (resultObj as Record<string, unknown>) : undefined;
  } catch {
    // parse failure is expected for non-JSON results
    return undefined;
  }
}

function recordKanbanTaskCreated(message: Message, result: unknown): void {
  const resultObj = readJsonObject(result);
  const task = resultObj?.task;
  if (resultObj?.status !== 'added' || !task || typeof task !== 'object') {
    return;
  }
  const { task_id: taskId, board_id: boardId, title } = task as Record<string, unknown>;
  if (typeof taskId !== 'string' || typeof boardId !== 'string' || typeof title !== 'string') {
    return;
  }
  const prior = message.metadata?.kanban_tasks_created;
  const list = Array.isArray(prior) ? [...prior] : prior ? [prior] : [];
  list.push({ task_id: taskId, title, board_id: boardId });
  message.metadata = { ...message.metadata, kanban_tasks_created: list };
}

function recordMemoryRecall(message: Message, data: ToolEndStreamEvent): void {
  if (Array.isArray(data.cited_memory_ids)) {
    const ids = data.cited_memory_ids.filter((id): id is string => typeof id === 'string' && id.length > 0);
    message.citedMemoryIds = [...new Set([...(message.citedMemoryIds ?? []), ...ids])];
  }

  const refs = H.normalizeCitedMemoryReferences(data.cited_memory_refs);
  if (refs.length > 0) {
    message.citedMemoryRefs = H.mergeCitedMemoryReferences(message.citedMemoryRefs, refs);
  }

  const trace = data.memory_retrieval_trace;
  if (trace && typeof trace.degraded === 'boolean' && trace.degraded) {
    message.memoryRetrievalDegraded = true;
  }
}

export function applyToolEndToMessage(message: Message, data: ToolEndStreamEvent): void {
  const steps = message.progressSteps;

  if (steps && typeof data.skill_mutation_batch_id === 'string') {
    linkSkillManageBatch(steps, data.skill_mutation_batch_id);
  }

  const kanbanSoftError = data.tool_name === 'kanban_add_task' ? readKanbanSoftError(data.result) : undefined;

  if (steps && steps.length > 0) {
    const lastStep = steps[steps.length - 1];
    if (data.duration_ms != null) {
      lastStep.duration_ms = data.duration_ms;
    }
    if (kanbanSoftError) {
      lastStep.status = 'error';
      lastStep.error = kanbanSoftError;
    } else if (data.duration_ms != null && !lastStep.status) {
      lastStep.status = 'success';
    }
  }

  if (data.tool_name === 'cron_manage' && data.result) {
    const resultObj = readJsonObject(data.result);
    if (resultObj?.status === 'success') {
      message.metadata = { ...message.metadata, cron_job_result: resultObj };
    }
  }

  if (data.tool_name === 'kanban_add_task' && data.result) {
    recordKanbanTaskCreated(message, data.result);
  }

  // MCP Apps (ext-apps): detect mcp_app metadata and attach view to message
  const mcpApp = data.mcp_app;
  if (mcpApp && mcpApp.resource_uri) {
    const view = {
      resourceUri: mcpApp.resource_uri,
      serverName: mcpApp.server_name ?? '',
      structuredContent: mcpApp.structured_content,
      toolName: data.tool_name,
    };
    message.mcpApps = [...(message.mcpApps ?? []), view];
  }

  if (H.isMemoryRecallToolName(data.tool_name)) {
    recordMemoryRecall(message, data);
  }
}
