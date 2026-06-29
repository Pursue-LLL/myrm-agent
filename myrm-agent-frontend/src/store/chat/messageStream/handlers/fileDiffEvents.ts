/**
 * [POS]
 * Chat SSE event handler slice (fileDiffEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function fileDiffEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, added, state, actions } = ctx;
  if (data.type === H.AgentEventType.FILE_DIFF) {
    const diffData = data.data;
    /** When FILE_DIFF arrives before TASKS_STEPS/ROUTING creates the assistant row, avoid attaching
     *  the diff to the *previous* turn's assistant (last assistant before the trailing user message). */
    let createdAssistantForDiff = false;

    actions.setMessages((state) => {
      let messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: state.messages[0]?.chatId || '',
          role: 'assistant',
          progressSteps: [],
          createdAt: new Date(),
        });
        messageIndex = state.messages.length - 1;
        createdAssistantForDiff = true;
      }
      const message = state.messages[messageIndex];
      if (!message.progressSteps) {
        message.progressSteps = [];
      }
      const steps = message.progressSteps;

      let matched = false;
      for (let i = steps.length - 1; i >= 0 && !matched; i -= 1) {
        const step = steps[i];
        if (!step.items || !Array.isArray(step.items)) {
          continue;
        }
        for (const raw of step.items) {
          const fp = H.parseProgressFilePath(raw);
          if (!fp || !H.pathsMatchForFileDiff(diffData.path, fp)) {
            continue;
          }
          if (raw && typeof raw === 'object' && 'file_path' in raw) {
            const row = raw as H.ProgressFileItem;
            const picked = H.pickMergedFileDiffPayload(
              { diff: row.diff, diff_truncated: row.diff_truncated },
              diffData.diff,
              Boolean(diffData.truncated),
            );
            row.diff = picked.diff;
            row.diff_truncated = picked.diff_truncated;
            matched = true;
            break;
          }
        }
      }

      if (!matched) {
        steps.push({
          step_key: 'file_diff',
          tool_name: null,
          items: [
            {
              file_path: diffData.path,
              action_type: 'write',
              diff: diffData.diff,
              ...(diffData.truncated ? { diff_truncated: true } : {}),
            },
          ],
        });
      }

      const diffArtifactId = `mem-diff-${diffData.path}`;
      const portalState = H.useArtifactPortalStore.getState();
      const mergedRow = (() => {
        for (let i = steps.length - 1; i >= 0; i -= 1) {
          const step = steps[i];
          if (!step.items || !Array.isArray(step.items)) continue;
          for (const raw of step.items) {
            const fp = H.parseProgressFilePath(raw);
            if (!fp || !H.pathsMatchForFileDiff(diffData.path, fp)) continue;
            if (raw && typeof raw === 'object' && 'file_path' in raw) {
              const row = raw as H.ProgressFileItem;
              if (row.diff) {
                return { diff: row.diff, truncated: Boolean(row.diff_truncated) };
              }
            }
          }
        }
        return { diff: diffData.diff, truncated: Boolean(diffData.truncated) };
      })();
      if (portalState.openTabs.some((t) => t.artifact.id === diffArtifactId)) {
        portalState.updateTabContent(diffArtifactId, mergedRow.diff, {
          truncated: mergedRow.truncated,
        });
      }
    });
    ctx.added = added || createdAssistantForDiff;
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_IMAGE_OUTPUT) {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) return done(ctx);

    const message = state.messages[messageIndex];
    const imgEntry: import('@/store/chat/types').ToolImageOutput = {
      base64: data.data.base64,
      mimeType: data.data.mime_type,
      toolName: data.tool_name,
    };
    message.toolImages = [...(message.toolImages ?? []), imgEntry];
    return done(ctx);
  }

  if (data.type === H.AgentEventType.BROWSER_VIEW_UPDATE) {
    const { default: useBrowserInspectorStore } = await import('@/store/useBrowserInspectorStore');
    const store = useBrowserInspectorStore.getState();
    store.setBrowserActive(true);
    store.updateViewData({
      screenshotBase64: data.data.screenshot_base64,
      mimeType: data.data.mime_type,
      refs: data.data.refs,
      pageUrl: data.data.page_url,
      pageTitle: data.data.page_title,
      viewportWidth: data.data.viewport_width,
      viewportHeight: data.data.viewport_height,
      updatedAt: Date.now(),
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.DESKTOP_VIEW_UPDATE) {
    const { default: useDesktopInspectorStore } = await import('@/store/useDesktopInspectorStore');
    const store = useDesktopInspectorStore.getState();
    store.setDesktopActive(true);
    store.updateViewData({
      screenshotBase64: data.data.screenshot_base64,
      mimeType: data.data.mime_type,
      refs: data.data.refs,
      appName: data.data.app_name,
      windowTitle: data.data.window_title,
      scope: data.data.scope,
      needsPermission: data.data.needs_permission,
      viewportWidth: data.data.viewport_width,
      viewportHeight: data.data.viewport_height,
      screenWidth: data.data.screen_width,
      screenHeight: data.data.screen_height,
      dpiScale: data.data.dpi_scale,
      updatedAt: Date.now(),
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.BROWSER_TAKEOVER_REQUESTED) {
    const { default: useBrowserTakeoverStore } = await import('@/store/useBrowserTakeoverStore');
    useBrowserTakeoverStore.getState().requestTakeover({
      reason: data.data.reason,
      screenshot_base64: data.data.screenshot_base64,
      url: data.data.url,
      messageId: data.messageId,
    });
    const { fetchWithTimeout } = await import('@/lib/api');
    fetchWithTimeout('/webui/vnc/takeover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: data.data.reason || '' }),
    }).catch(() => {});
    return done(ctx);
  }

  if (data.type === H.AgentEventType.BROWSER_TAKEOVER_COMPLETED) {
    const { default: useBrowserTakeoverStore } = await import('@/store/useBrowserTakeoverStore');
    useBrowserTakeoverStore.getState().completeTakeover();
    return done(ctx);
  }


  return null;
}
