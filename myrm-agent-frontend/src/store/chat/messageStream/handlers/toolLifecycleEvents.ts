/**
 * [POS]
 * Chat SSE event handler slice (toolLifecycleEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function toolLifecycleEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, state } = ctx;
  if (data.type === H.AgentEventType.TOOL_START) {
    ctx.recievedMessage = '';

    const toolName = data.tool_name ?? '';
    const streamChatId = state.messages[0]?.chatId?.trim() ?? '';
    if (toolName.startsWith('browser_')) {
      const { default: inspectorStore } = await import('@/store/useBrowserInspectorStore');
      const { default: useChatStore } = await import('@/store/useChatStore');
      inspectorStore.getState().setBrowserActive(true);
      inspectorStore.getState().markTurnEngaged(streamChatId);
      const activeChatId = useChatStore.getState().chatId?.trim() ?? '';
      if (streamChatId && activeChatId && streamChatId === activeChatId) {
        inspectorStore.getState().openPanel();
      }
    }
    if (toolName.startsWith('desktop_')) {
      const { default: desktopStore } = await import('@/store/useDesktopInspectorStore');
      desktopStore.getState().setDesktopActive(true);
      desktopStore.getState().markTurnEngaged(streamChatId);
    }

    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_END) {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) {return done(ctx);}

    const message = state.messages[messageIndex];
    const steps = message.progressSteps;

    let kanbanSoftError: string | undefined;
    if (data.tool_name === 'kanban_add_task' && data.result) {
      try {
        const resultObj = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
        if (
          resultObj &&
          typeof resultObj === 'object' &&
          typeof (resultObj as { error?: unknown }).error === 'string'
        ) {
          const errText = (resultObj as { error: string }).error.trim();
          if (errText) {
            kanbanSoftError = errText;
          }
        }
      } catch {
        // parse failure is expected for non-kanban results
      }
    }

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

    if (
      data.tool_name?.startsWith('desktop_') &&
      data.tool_name !== 'desktop_snapshot_tool'
    ) {
      // desktop_snapshot_tool already pushed refs via DESKTOP_VIEW_UPDATE SSE;
      // re-fetch here would re-capture the wrong foreground window (e.g. Chrome).
      const { default: desktopStore } = await import('@/store/useDesktopInspectorStore');
      const { default: useChatStore } = await import('@/store/useChatStore');
      const streamChatId = state.messages[0]?.chatId?.trim() ?? '';
      const activeChatId = useChatStore.getState().chatId?.trim() ?? '';
      if (streamChatId && activeChatId && streamChatId === activeChatId) {
        void desktopStore.getState().fetchSnapshot();
      }
    }

    if (data.tool_name === 'cron_manage' && data.result) {
      try {
        const resultObj = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
        if (resultObj && resultObj.status === 'success') {
          message.metadata = {
            ...message.metadata,
            cron_job_result: resultObj,
          };
        }
      } catch {
        // parse failure is expected for non-cron results
      }
    }

    if (data.tool_name === 'kanban_add_task' && data.result) {
      try {
        const resultObj = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
        const task = resultObj?.task;
        if (resultObj?.status === 'added' && task && typeof task === 'object' && task !== null) {
          const taskRecord = task as Record<string, unknown>;
          const taskId = taskRecord.task_id;
          const boardId = taskRecord.board_id;
          const title = taskRecord.title;
          if (typeof taskId === 'string' && typeof boardId === 'string' && typeof title === 'string') {
            const created = {
              task_id: taskId,
              title,
              board_id: boardId,
            };
            const prior = message.metadata?.kanban_tasks_created;
            const list = Array.isArray(prior) ? [...prior] : prior ? [prior] : [];
            list.push(created);
            message.metadata = {
              ...message.metadata,
              kanban_tasks_created: list,
            };
          }
        }
      } catch {
        // parse failure is expected for non-kanban results
      }
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
      if (Array.isArray(data.cited_memory_ids)) {
        const ids = data.cited_memory_ids.filter((id): id is string => typeof id === 'string' && id.length > 0);
        const existing = message.citedMemoryIds ?? [];
        message.citedMemoryIds = [...new Set([...existing, ...ids])];
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

    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_FAILURE) {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) {return done(ctx);}

    const steps = state.messages[messageIndex].progressSteps;
    if (steps && steps.length > 0) {
      const lastStep = steps[steps.length - 1];
      if (data.duration_ms != null) {
        lastStep.duration_ms = data.duration_ms;
      }
      lastStep.status = 'error';
      lastStep.error = data.error;
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_STDOUT_CHUNK) {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) {return done(ctx);}

    const steps = state.messages[messageIndex].progressSteps;
    if (steps && steps.length > 0) {
      const lastStep = steps[steps.length - 1];
      const newStdout = (lastStep.stdout || '') + data.data;
      if (newStdout.length > 30000) {
        const sliced = newStdout.slice(-30000);
        const newlineIndex = sliced.indexOf('\n');
        const safeTruncated = newlineIndex !== -1 ? sliced.substring(newlineIndex + 1) : sliced;
        lastStep.stdout = '...[Terminal output truncated to preserve memory]...\n' + safeTruncated;
      } else {
        lastStep.stdout = newStdout;
      }
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_EVICTED_REF) {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) {return done(ctx);}

    const steps = state.messages[messageIndex].progressSteps;
    if (!steps || steps.length === 0) {return done(ctx);}

    const rawPayload = data.data as unknown;
    let ref: string | undefined;
    let toolCallId: string | undefined;
    let previewStdout: string | undefined;
    let toolName: string | undefined;
    let storedChars: number | undefined;
    let totalLines: number | undefined;
    let storageTruncated: boolean | undefined;
    let stream: string | undefined;

    if (typeof rawPayload === 'string') {
      ref = rawPayload;
    } else if (rawPayload && typeof rawPayload === 'object') {
      const payload = rawPayload as Record<string, unknown>;
      if (typeof payload.evicted_ref === 'string') {
        ref = payload.evicted_ref;
      }
      if (typeof payload.tool_call_id === 'string') {
        toolCallId = payload.tool_call_id;
      }
      if (typeof payload.preview_stdout === 'string') {
        previewStdout = payload.preview_stdout;
      }
      if (typeof payload.tool_name === 'string') {
        toolName = payload.tool_name;
      }
      if (typeof payload.stored_chars === 'number' && payload.stored_chars > 0) {
        storedChars = payload.stored_chars;
      }
      if (typeof payload.total_lines === 'number' && payload.total_lines > 0) {
        totalLines = payload.total_lines;
      }
      if (payload.storage_truncated === true) {
        storageTruncated = true;
      }
      if (typeof payload.stream === 'string') {
        stream = payload.stream;
      }
    }

    if (!ref) {
      return done(ctx);
    }

    const isStderr = stream === 'stderr';

    let target =
      toolCallId !== undefined
        ? steps.find((step) => step.tool_call_id === toolCallId)
        : undefined;
    if (!target && toolName) {
      for (let index = steps.length - 1; index >= 0; index -= 1) {
        const step = steps[index];
        if (step.tool_name === toolName) {
          const alreadyClaimed = isStderr
            ? step.evicted_stderr_file_ref
            : step.evicted_file_ref;
          if (!alreadyClaimed) {
            target = step;
            break;
          }
        }
      }
    }
    if (!target) {
      target = steps[steps.length - 1];
    }

    if (isStderr) {
      target.evicted_stderr_file_ref = ref;
      if (storedChars !== undefined) {
        target.evicted_stderr_stored_chars = storedChars;
      }
      if (totalLines !== undefined) {
        target.evicted_stderr_total_lines = totalLines;
      }
      if (storageTruncated === true) {
        target.evicted_stderr_storage_truncated = true;
      }
      return done(ctx);
    }

    target.evicted_file_ref = ref;
    if (previewStdout) {
      target.stdout = previewStdout;
    }
    if (storedChars !== undefined) {
      target.evicted_stored_chars = storedChars;
    }
    if (totalLines !== undefined) {
      target.evicted_total_lines = totalLines;
    }
    if (storageTruncated === true) {
      target.evicted_storage_truncated = true;
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_CANCELLED) {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) {return done(ctx);}

    const steps = state.messages[messageIndex].progressSteps;
    if (steps && steps.length > 0) {
      const lastStep = steps[steps.length - 1];
      if (data.duration_ms != null) {
        lastStep.duration_ms = data.duration_ms;
      }
      lastStep.status = 'warning';

      // Format error message with cancel reason
      const cancelReason = data.cancel_reason;
      let errorMsg = 'Tool execution was cancelled';
      if (cancelReason === 'user_cancelled') {
        errorMsg = 'Cancelled by user';
      } else if (cancelReason === 'timeout') {
        errorMsg = 'Cancelled (timeout)';
      } else if (cancelReason === 'session_ended') {
        errorMsg = 'Cancelled (session ended)';
      } else if (data.error) {
        errorMsg = data.error;
      }
      lastStep.error = errorMsg;
    }
    return done(ctx);
  }


  return null;
}
