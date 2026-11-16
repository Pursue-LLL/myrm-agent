/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useDesktopInspectorStore::useDesktopInspectorStore, selectScopedDesktopViewData (POS: State management for the Desktop Live View + Interactive Inspector feature.)
 * - @/store/useBrowserInspectorStore::useBrowserInspectorStore, selectScopedBrowserViewData (POS: State management for the Browser Live View + Interactive Inspector feature.)
 * - @/store/chat/types::AgentEventType, BrowserRefInfo (POS: @/store/chat/types 稳定入口；实现位于 types/。)
 * - @/store/chat/messageStream/streamContext::StreamCtx (POS: Shared context for messageStream/handlers/* event slices.)
 * - @/store/chat/messageStream/types::StreamHandlerState (POS: Type definitions for the chat message stream handler subsystem.)
 * - @/store/chat/messageStream/handlers/fileDiffEvents::fileDiffEvents (POS: Chat SSE event handler slice (fileDiffEvents)。)
 * - @/store/chat/messageStream/handlers/toolLifecycleEvents::toolLifecycleEvents (POS: Chat SSE event handler slice (toolLifecycleEvents).)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createInspectorMembers(): browser and desktop inspector snapshots plus view / tool / approval simulators driven through the real event paths
 *
 * [POS]
 * 桥成员（检查器）：浏览器与桌面检查器快照，以及经真实事件通路驱动的视图、工具与审批模拟。
 */
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore, { selectScopedDesktopViewData } from '@/store/useDesktopInspectorStore';
import useBrowserInspectorStore, { selectScopedBrowserViewData } from '@/store/useBrowserInspectorStore';
import type { BrowserRefInfo } from '@/store/chat/types';
import type { StreamCtx } from '@/store/chat/messageStream/streamContext';
import type { StreamHandlerState } from '@/store/chat/messageStream/types';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

/** Handler context of a simulated stream event: one assistant message of `chatId`, every store action a no-op. */
function buildSimulatedStreamContext(chatId: string, messageId: string, loading = false): Omit<StreamCtx, 'data'> {
  return {
    input: '',
    sources: undefined,
    added: false,
    state: {
      messages: [
        {
          messageId,
          chatId,
          role: 'assistant',
          content: '',
          createdAt: new Date(),
        },
      ],
      messageAppeared: false,
      loading,
      scheduler: {} as StreamHandlerState['scheduler'],
    },
    actions: {
      setMessages: () => undefined,
      setMessageAppeared: () => undefined,
      setLoading: () => undefined,
      _processSuggestions: async () => undefined,
      scheduleAutoSave: () => undefined,
    },
    recievedMessage: '',
    files: [],
  };
}

export function createInspectorMembers(): E2eBridgeMembers {
  return {
    getBrowserInspectorSnapshot: () => {
      const store = useBrowserInspectorStore.getState();
      const activeChatId = useChatStore.getState().chatId?.trim() ?? '';
      const scopedView = selectScopedBrowserViewData(store.viewData, activeChatId);
      const refs = store.viewData?.refs ?? {};
      return {
        isOpen: store.isOpen,
        isBrowserActive: store.isBrowserActive,
        hasScreenshot: Boolean(store.viewData?.screenshotBase64),
        scopedHasScreenshot: Boolean(scopedView?.screenshotBase64),
        sourceChatId: store.viewData?.sourceChatId ?? '',
        activeChatId,
        pageUrl: store.viewData?.pageUrl ?? '',
        pageTitle: store.viewData?.pageTitle ?? '',
        refCount: Object.keys(refs).length,
        updatedAt: store.viewData?.updatedAt ?? null,
      };
    },
    simulateBrowserViewUpdate: async (
      chatId: string,
      refs: Record<string, BrowserRefInfo> = {},
      screenshotBase64 = 'e2e-blvc-screenshot',
    ) => {
      const normalizedChatId = chatId.trim();
      if (!normalizedChatId) {
        return { ok: false as const, reason: 'empty-chat-id' };
      }
      const { fileDiffEvents } = await import('@/store/chat/messageStream/handlers/fileDiffEvents');
      const { AgentEventType } = await import('@/store/chat/types');
      const messageId = `e2e-blvc-view-${Date.now()}`;
      await fileDiffEvents({
        data: {
          type: AgentEventType.BROWSER_VIEW_UPDATE,
          messageId,
          data: {
            screenshot_base64: screenshotBase64,
            mime_type: 'image/png',
            refs,
            page_url: 'https://e2e.example/blcv',
            page_title: 'BLCV E2E',
            viewport_width: 1280,
            viewport_height: 720,
          },
        },
        ...buildSimulatedStreamContext(normalizedChatId, messageId),
      });
      if (Object.keys(refs).length > 0) {
        useBrowserInspectorStore.getState().setMode('inspect');
      }
      return { ok: true as const, chatId: normalizedChatId };
    },
    simulateBrowserToolStart: async (chatId: string, toolName = 'browser_navigate_tool') => {
      const normalizedChatId = chatId.trim();
      const normalizedTool = toolName.trim();
      if (!normalizedChatId || !normalizedTool.startsWith('browser_')) {
        return { ok: false as const, reason: 'invalid-args' };
      }
      const { toolLifecycleEvents } = await import('@/store/chat/messageStream/handlers/toolLifecycleEvents');
      const { AgentEventType } = await import('@/store/chat/types');
      const messageId = `e2e-blvc-tool-${Date.now()}`;
      await toolLifecycleEvents({
        data: {
          type: AgentEventType.TOOL_START,
          messageId,
          tool_name: normalizedTool,
        },
        ...buildSimulatedStreamContext(normalizedChatId, messageId),
      });
      return { ok: true as const, chatId: normalizedChatId, toolName: normalizedTool };
    },
    getDesktopInspectorSnapshot: () => {
      const store = useDesktopInspectorStore.getState();
      const activeChatId = useChatStore.getState().chatId?.trim() ?? '';
      const scopedView = selectScopedDesktopViewData(store.viewData, activeChatId);
      const refs = store.viewData?.refs ?? {};
      return {
        isOpen: store.isOpen,
        isDesktopActive: store.isDesktopActive,
        hasScreenshot: Boolean(store.viewData?.screenshotBase64),
        scopedHasScreenshot: Boolean(scopedView?.screenshotBase64),
        sourceChatId: store.viewData?.sourceChatId ?? '',
        activeChatId,
        appName: store.viewData?.appName ?? '',
        refCount: Object.keys(refs).length,
        updatedAt: store.viewData?.updatedAt ?? null,
      };
    },
    simulateDesktopViewUpdate: async (chatId: string) => {
      const normalizedChatId = chatId.trim();
      if (!normalizedChatId) {
        return { ok: false as const, reason: 'empty-chat-id' };
      }
      const { fileDiffEvents } = await import('@/store/chat/messageStream/handlers/fileDiffEvents');
      const { AgentEventType } = await import('@/store/chat/types');
      const messageId = `e2e-blvc-desktop-${Date.now()}`;
      await fileDiffEvents({
        data: {
          type: AgentEventType.DESKTOP_VIEW_UPDATE,
          messageId,
          data: {
            screenshot_base64: 'e2e-blvc-desktop-screenshot',
            mime_type: 'image/jpeg',
            refs: {},
            app_name: 'E2E App',
            window_title: 'BLCV Desktop E2E',
            scope: 'screen',
            needs_permission: false,
            viewport_width: 1280,
            viewport_height: 720,
          },
        },
        ...buildSimulatedStreamContext(normalizedChatId, messageId),
      });
      return { ok: true as const, chatId: normalizedChatId };
    },
    simulateDesktopControlApprovalRequest: async (chatId: string) => {
      const normalizedChatId = chatId.trim();
      if (!normalizedChatId) {
        return { ok: false as const, reason: 'empty-chat-id' };
      }
      const { fileDiffEvents } = await import('@/store/chat/messageStream/handlers/fileDiffEvents');
      const { AgentEventType } = await import('@/store/chat/types');
      const messageId = `e2e-blvc-desktop-approval-${Date.now()}`;
      await fileDiffEvents({
        data: {
          type: AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST,
          messageId,
          data: {
            request_id: `req-${Date.now()}`,
            reason: 'E2E desktop control',
            operation: 'control',
            app_name: 'E2E App',
            window_title: 'BLCV',
            require_app_approval: true,
          },
        },
        ...buildSimulatedStreamContext(normalizedChatId, messageId, true),
      });
      return { ok: true as const, chatId: normalizedChatId };
    },
  } as E2eBridgeMembers;
}
