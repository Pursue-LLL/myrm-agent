/**
 * [INPUT]
 * - @/store/chat/messageRequest::getModelSelection (POS: Facade of the chat message request layer.)
 * - @/store/chat/streamErrors::AgentBusyError (POS: Chat agent-stream 错误分类 SSOT（叶子模块），供 streamConsumer / consumeStream 与 HITL resume 共用。)
 * - @/store/chat/streamConsumer::executeStreamWithRetry (POS: Chat agent-stream 前端回合编排 SSOT。)
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useDesktopControlApprovalStore::useDesktopControlApprovalStore (POS: Manages SSE-driven desktop control approval requests (per-app + foreground gate).)
 * - @/store/useApprovalStore::useApprovalStore
 * - @/store/useBrowserTakeoverStore::useBrowserTakeoverStore (POS: Manages the state when Agent requests human takeover of the browser session.)
 * - @/store/useWorkspaceStore::useWorkspaceStore (POS: Workspace state manager.)
 * - @/store/useDesktopInspectorStore::useDesktopInspectorStore (POS: State management for the Desktop Live View + Interactive Inspector feature.)
 * - @/components/dev/e2eBridge/providerBootstrap::initProvidersForE2e (POS: 开发桥的 provider 与搜索服务引导)
 * - @/components/dev/e2eBridge/hostEnv::prepareAutomationSend (POS: 开发桥的页面环境探针)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createStreamControlMembers(): tool-progress snapshots, stream abort / release / same-id retry, shell state and approval drawer reads
 *
 * [POS]
 * 桥成员（流控制）：工具进度快照、流的中止与释放、同消息 id 重试、聊天外壳状态与审批抽屉读写。
 */
import { flushSync } from 'react-dom';
import { getModelSelection } from '@/store/chat/messageRequest';
import { AgentBusyError } from '@/store/chat/streamErrors';
import { executeStreamWithRetry } from '@/store/chat/streamConsumer';
import useChatStore from '@/store/useChatStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useApprovalStore from '@/store/useApprovalStore';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import { initProvidersForE2e } from '@/components/dev/e2eBridge/providerBootstrap';
import { prepareAutomationSend } from '@/components/dev/e2eBridge/hostEnv';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

export function createStreamControlMembers(): E2eBridgeMembers {
  return {
    getFastSearchProgressSnapshot: () => {
      const chat = useChatStore.getState();
      const assistants = chat.messages.filter((message) => message.role === 'assistant');
      const lastAssistant = assistants[assistants.length - 1];
      const metaSteps = Array.isArray(lastAssistant?.metadata?.progressSteps)
        ? lastAssistant.metadata.progressSteps
        : [];
      const steps = lastAssistant?.progressSteps?.length ? lastAssistant.progressSteps : metaSteps;
      const toolNames = steps.map((step) => String(step.tool_name ?? ''));
      const evictedRefs = steps
        .map((step) => step.evicted_file_ref)
        .filter((ref): ref is string => typeof ref === 'string' && ref.length > 0);
      const content = typeof lastAssistant?.content === 'string' ? lastAssistant.content : '';
      return {
        chatId: chat.chatId?.trim() || null,
        isStreaming: Boolean(chat.loading || chat.abortController),
        toolNames,
        evictedRefs,
        contentSample: content.slice(0, 240),
        mentionsGuido: /Guido van Rossum/i.test(content),
        hasAssistant: Boolean(lastAssistant),
      };
    },
    getDesktopToolProgress: () => {
      const approval = useDesktopControlApprovalStore.getState();
      const chat = useChatStore.getState();
      const messages = chat.messages;
      const assistants = messages.filter((message) => message.role === 'assistant');
      const lastAssistant = assistants[assistants.length - 1];
      const metaSteps = Array.isArray(lastAssistant?.metadata?.progressSteps)
        ? lastAssistant.metadata.progressSteps
        : [];
      const steps = lastAssistant?.progressSteps?.length ? lastAssistant.progressSteps : metaSteps;
      const desktopSteps = steps.filter((step) => String(step.tool_name ?? '').startsWith('desktop_'));
      const completionStatus = String(lastAssistant?.metadata?.completionStatus ?? '');
      const isComplete = completionStatus === 'complete';
      const isStreaming = !isComplete && Boolean(chat.loading || chat.abortController);
      return {
        active: desktopSteps.length > 0,
        isStreaming,
        pending: approval.pending,
        requestId: approval.requestId,
        stepCount: desktopSteps.length,
        lastTool: desktopSteps[desktopSteps.length - 1]?.tool_name ?? '',
      };
    },
    getFirstDesktopDref: () => {
      const pickDref = (refs: Record<string, { role?: string; name?: string }> | undefined): string | null => {
        if (!refs || typeof refs !== 'object') {
          return null;
        }
        const preferredRoles = new Set(['text', 'statictext', 'axtextarea', 'scrollarea']);
        for (const [refId, info] of Object.entries(refs)) {
          const role = String(info?.role ?? '').toLowerCase();
          const normalized = refId.trim().replace(/^@/, '');
          if (preferredRoles.has(role) && normalized.startsWith('d') && normalized.length > 1) {
            return normalized;
          }
        }
        for (const refId of Object.keys(refs).sort()) {
          const normalized = refId.trim().replace(/^@/, '');
          if (normalized.startsWith('d') && normalized.length > 1) {
            return normalized;
          }
        }
        return null;
      };

      const e2eRefs = window.__MYRM_E2E_DESKTOP_REFS__?.refs;
      const fromE2eCache = pickDref(e2eRefs);
      if (fromE2eCache) {
        return fromE2eCache;
      }

      const viewData = useDesktopInspectorStore.getState().viewData;
      return pickDref(viewData?.refs);
    },
    getBrowserToolProgress: () => {
      const takeover = useBrowserTakeoverStore.getState();
      const messages = useChatStore.getState().messages;
      const assistants = messages.filter((message) => message.role === 'assistant');
      const lastAssistant = assistants[assistants.length - 1];
      const steps = lastAssistant?.progressSteps ?? [];
      const browserSteps = steps.filter((step) => String(step.tool_name ?? '').startsWith('browser_'));
      return {
        active: browserSteps.length > 0,
        takeoverPending: takeover.pending,
        takeoverUiMode: takeover.pending ? takeover.uiMode : null,
        stepCount: browserSteps.length,
        lastTool: browserSteps[browserSteps.length - 1]?.tool_name ?? '',
      };
    },
    abortActiveStream: () => {
      useChatStore.getState().stopMessage();
    },
    /** Close in-flight SSE only (no cancel API) so a separate agent-stream resume can proceed. */
    releaseActiveStreamForApiResume: () => {
      const chatState = useChatStore.getState();
      const paneId = useWorkspaceStore.getState().panes.find((pane) => pane.chatId === chatState.chatId)?.id;
      const paneAbort =
        paneId !== null && paneId !== undefined ? useWorkspaceStore.getState().getPaneAbortController(paneId) : null;
      const controller = paneAbort ?? chatState.abortController;
      let released = false;
      if (controller && !controller.signal.aborted) {
        controller.abort();
        released = true;
      }
      flushSync(() => {
        useChatStore.setState({
          loading: false,
          abortController: null,
          messageAppeared: true,
        });
      });
      if (paneId) {
        useWorkspaceStore.getState().setPaneAbortController(paneId, null);
      }
      return { ok: true, released };
    },
    retryStreamWithSameMessageId: async (query: string, messageId: string) => {
      await initProvidersForE2e();
      prepareAutomationSend();
      const trimmedId = messageId.trim();
      const trimmedQuery = query.trim();
      if (!trimmedId || !trimmedQuery) {
        return { ok: false, busy: false, err: 'empty-query-or-message-id' };
      }
      const state = useChatStore.getState();
      const modelSelection = getModelSelection(state.actionMode, state.agentConfig);
      if (!modelSelection) {
        return { ok: false, busy: false, err: 'no-model-selection' };
      }
      const abortController = new AbortController();
      const actions = {
        setMessages: useChatStore.getState().setMessages,
        setLoading: (loading: boolean) => useChatStore.setState({ loading }),
        setMessageAppeared: (appeared: boolean) => useChatStore.setState({ messageAppeared: appeared }),
        setHideAttachList: (hide: boolean) => useChatStore.setState({ hideAttachList: hide }),
        setHasUsedImagesInCurrentChat: (hasUsed: boolean) =>
          useChatStore.setState({ hasUsedImagesInCurrentChat: hasUsed }),
        setSelectedModels: (models: typeof state.selectedModels) => useChatStore.setState({ selectedModels: models }),
        setHasUserSelectedModel: (hasSelected: boolean) => useChatStore.setState({ hasUserSelectedModel: hasSelected }),
        clearCurrentSessionMessageId: () => useChatStore.setState({ currentSessionMessageId: null }),
        setIsWorkflowMode: (enabled: boolean) => useChatStore.setState({ isWorkflowMode: enabled }),
        clearPendingWorkflowTemplate: () =>
          useChatStore.setState({
            pendingWorkflowTemplateId: null,
            pendingWorkflowTemplateDisplayName: null,
            pendingWorkflowTemplateArgs: null,
          }),
        _processSuggestions: useChatStore.getState()._processSuggestions,
        scheduleAutoSave: useChatStore.getState().scheduleAutoSave,
        setInputMessage: (message: string) => useChatStore.setState({ inputMessage: message }),
      };
      try {
        await executeStreamWithRetry(
          trimmedQuery,
          trimmedId,
          state,
          actions,
          modelSelection,
          abortController,
          false,
          '',
        );
        return { ok: true, busy: false };
      } catch (error) {
        if (error instanceof AgentBusyError) {
          return { ok: false, busy: true, err: error.message };
        }
        return {
          ok: false,
          busy: false,
          err: error instanceof Error ? error.message : String(error),
        };
      } finally {
        abortController.abort();
      }
    },
    getChatShellState: () => {
      const state = useChatStore.getState();
      let artifactCount = 0;
      let htmlArtifactWithPath = false;
      for (const message of state.messages) {
        const artifacts = message.artifacts ?? [];
        artifactCount += artifacts.length;
        if (
          artifacts.some(
            (artifact) =>
              artifact.type === 'html' && typeof artifact.file_path === 'string' && artifact.file_path.length > 0,
          )
        ) {
          htmlArtifactWithPath = true;
        }
      }
      return {
        chatId: state.chatId?.trim() || null,
        notFound: state.notFound,
        loadError: state.loadError,
        isMessagesLoaded: state.isMessagesLoaded,
        loading: state.loading,
        messageCount: state.messages.length,
        artifactCount,
        htmlArtifactWithPath,
      };
    },
    setLoading: (loading: boolean) => {
      useChatStore.setState({ loading });
    },
    hideApprovalDrawer: () => {
      flushSync(() => {
        useApprovalStore.getState().hideDrawer();
      });
    },
    isApprovalDrawerOpen: () => useApprovalStore.getState().isOpen,
    getDesktopApprovalSnapshot: () => {
      const state = useDesktopControlApprovalStore.getState();
      return {
        pending: state.pending,
        requestId: state.requestId,
        reason: state.reason,
        operation: state.operation,
        appName: state.appName,
        requireAppApproval: state.requireAppApproval,
      };
    },
    syncDesktopControlApproval: (payload: {
      request_id: string;
      reason: string;
      operation: string;
      app_name?: string;
      window_title?: string;
      require_app_approval?: boolean;
    }) => {
      useDesktopControlApprovalStore.getState().requestApproval({
        request_id: payload.request_id,
        reason: payload.reason,
        operation: payload.operation,
        app_name: payload.app_name,
        window_title: payload.window_title,
        require_app_approval: payload.require_app_approval,
      });
      void import('@/store/useDesktopInspectorStore').then(({ default: useDesktopInspectorStore }) => {
        useDesktopInspectorStore.getState().openPanel();
      });
    },
  } as E2eBridgeMembers;
}
