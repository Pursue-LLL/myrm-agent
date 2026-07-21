/**
 * [INPUT]
 * - handlerDeps (POS: SSE handler 切片共享依赖)
 * - useBrowserTakeoverStore (POS: 浏览器 HITL takeover 请求状态)
 *
 * [OUTPUT]
 * fileDiffEvents: FILE_DIFF / TOOL_IMAGE / BROWSER_TAKEOVER SSE 切片（含 extension live-assist 链接生成）
 *
 * [POS]
 * Chat SSE event handler slice (fileDiffEvents)。
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";
import { takeoverVncOpenFailedMessage } from "./takeoverVncMessages";

async function notifyTakeoverVncOpenFailed(): Promise<void> {
  const { getClientLocale } = await import("@/lib/utils/localeUtils");
  const { toast } = await import("@/lib/utils/toast");
  toast.error(takeoverVncOpenFailedMessage(getClientLocale()), { duration: 8000 });
}

function clampTakeoverContextValue(value: string, maxLength: number): string {
  const trimmed = value.trim();
  return trimmed ? trimmed.slice(0, maxLength) : '';
}

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
          tool_name: undefined,
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
      ...(data.data.base64 ? { base64: data.data.base64 } : {}),
      ...(data.data.url ? { url: data.data.url } : {}),
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

  if (data.type === H.AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST) {
    const { default: useDesktopControlApprovalStore } = await import(
      '@/store/useDesktopControlApprovalStore'
    );
    const approvalPayload = {
      request_id: String(data.data.request_id ?? ''),
      reason: String(data.data.reason ?? ''),
      operation: String(data.data.operation ?? ''),
      app_name: data.data.app_name ? String(data.data.app_name) : '',
      window_title: data.data.window_title ? String(data.data.window_title) : '',
      require_app_approval: Boolean(data.data.require_app_approval ?? true),
      messageId: data.messageId,
    };
    useDesktopControlApprovalStore.getState().requestApproval(approvalPayload);

    const { default: useDesktopInspectorStore } = await import('@/store/useDesktopInspectorStore');
    useDesktopInspectorStore.getState().openPanel();

    actions.setLoading(false);

    if (H.useConfigStore.getState().enableWebNotifications) {
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const { getDesktopControlApprovalNotificationTitle } = await import('@/lib/i18n/streamNotificationCopy');
      const title = getDesktopControlApprovalNotificationTitle(lang);
      const body = approvalPayload.app_name
        ? `${approvalPayload.app_name}${approvalPayload.window_title ? ` — ${approvalPayload.window_title}` : ''}`
        : approvalPayload.reason;
      import('@/services/notification').then(({ notificationService }) => {
        notificationService.notify(title, { body, fallbackToToast: false });
      });
    }

    if (typeof window !== 'undefined') {
      setTimeout(
        () => window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: 'approval_waiting' } })),
        0,
      );
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.BROWSER_TAKEOVER_REQUESTED) {
    const { activateBrowserTakeover } = await import('@/store/useApprovalStore');
    const isManaged = Boolean(data.data.is_managed);
    const uiMode = isManaged ? 'managed' : 'extension';
    const autoDetectCompletion = Boolean(data.data.auto_detect_completion);
    const eventReason = typeof data.data.reason === 'string' ? data.data.reason : '';
    const eventPageUrl = typeof data.data.url === 'string' ? data.data.url : '';
    const normalizedReason = clampTakeoverContextValue(eventReason, 280);
    const normalizedPageUrl = clampTakeoverContextValue(eventPageUrl, 1024);

    activateBrowserTakeover({
      reason: eventReason,
      url: eventPageUrl || undefined,
      screenshot_base64:
        typeof data.data.screenshot_base64 === 'string' ? data.data.screenshot_base64 : undefined,
      messageId: typeof data.messageId === 'string' ? data.messageId : undefined,
      is_managed: isManaged,
      auto_detect_completion: autoDetectCompletion,
      live_assist_url:
        typeof data.data.live_assist_url === 'string' ? data.data.live_assist_url : undefined,
    });

    actions.setLoading(false);
    if (typeof window !== 'undefined') {
      setTimeout(
        () => window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: 'approval_waiting' } })),
        0,
      );
    }

    if (uiMode === 'managed') {
      const { fetchWithTimeout } = await import('@/lib/api');
      void fetchWithTimeout('/webui/vnc/takeover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: data.data.reason || '' }),
      }).then(async (res) => {
        if (!res.ok) {
          await notifyTakeoverVncOpenFailed();
        }
      }).catch(async () => {
        await notifyTakeoverVncOpenFailed();
      });
    } else {
      const { default: useChatStore } = await import('@/store/useChatStore');
      const fallbackChatId = state.messages[0]?.chatId?.trim() ?? '';
      const chatId = useChatStore.getState().chatId?.trim() || fallbackChatId;
      if (chatId) {
        void (async () => {
          try {
            const { default: useBrowserTakeoverStore } = await import('@/store/useBrowserTakeoverStore');
            const currentLiveAssistUrl = useBrowserTakeoverStore.getState().liveAssistUrl;
            if (currentLiveAssistUrl) {
              return;
            }

            const { remoteAccessService } = await import('@/services/remoteAccess');
            const issued = await remoteAccessService.createPairingToken(chatId, 'browser_takeover');
            const rawPath = issued.mobileUrl || issued.mobilePath;
            if (!rawPath) {
              return;
            }

            const absoluteBase =
              typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
            const absoluteUrl =
              rawPath.startsWith('http://') || rawPath.startsWith('https://')
                ? rawPath
                : `${absoluteBase}${rawPath.startsWith('/') ? rawPath : `/${rawPath}`}`;
            const takeoverUrl = new URL(absoluteUrl, absoluteBase);
            if (typeof data.messageId === 'string' && data.messageId.trim()) {
              takeoverUrl.searchParams.set('mid', data.messageId.trim());
            }
            if (normalizedReason) {
              takeoverUrl.searchParams.set('reason', normalizedReason);
            }
            if (normalizedPageUrl) {
              takeoverUrl.searchParams.set('page', normalizedPageUrl);
            }
            useBrowserTakeoverStore.getState().setLiveAssistUrl(takeoverUrl.toString());
          } catch (error) {
            console.warn('[TAKEOVER] Failed to create browser takeover live link:', error);
          }
        })();
      }
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.BROWSER_TAKEOVER_COMPLETED) {
    const { default: useBrowserTakeoverStore } = await import('@/store/useBrowserTakeoverStore');
    useBrowserTakeoverStore.getState().completeTakeover();
    return done(ctx);
  }

  return null;
}
