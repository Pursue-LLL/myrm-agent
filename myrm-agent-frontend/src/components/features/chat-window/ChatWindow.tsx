'use client';

import { useEffect, useLayoutEffect, memo, useRef, useCallback, useState, useSyncExternalStore } from 'react';
import dynamic from 'next/dynamic';
import { useSearchParams, useRouter } from 'next/navigation';
import EmptyChat from './EmptyChat';
import MessageListSkeleton from './MessageListSkeleton';
import { Settings, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import NextError from 'next/error';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import { getAgent } from '@/services/agent';
import { AgentConfig } from '@/store/chat/types';
import { useSkillStore } from '@/store/skill';
import { validateAgentDependencies, buildMissingDependenciesParts } from '@/lib/utils/agentConfigValidator';
import { toast } from '@/hooks/shared/useToast';
import { useTranslations } from 'next-intl';
import { PermissionDialog } from '@/components/features/cli-agent/PermissionDialog';
import ToolApprovalDialog from './ToolApprovalDialog';
import ToolApprovalExpiryWatcher from './ToolApprovalExpiryWatcher';
import AgentInfoBanner from './AgentInfoBanner';
import YoloModeBanner from './YoloModeBanner';
import EStopBanner from './EStopBanner';
import ExtensionDisconnectedBanner from './ExtensionDisconnectedBanner';
import ExtensionTakeoverBanner from './ExtensionTakeoverBanner';
import { MemoryRecallDegradedBanner } from '@/components/features/message-box/MemoryRecallDegradedBanner';
import ChatWindowSatellites, { GoalControlPlane, GoalStatusCard, LifeStatusCapsule } from './ChatWindowSatellites';
import { ParentChatLink } from './ParentChatLink';
import { ChatCronLink } from './ChatCronLink';
import SessionRevertButton from '../message-actions/SessionRevertButton';
import WorkingStateBadge from './WorkingStateBadge';
import RunStatusChip from '@/components/features/copilot/RunStatusChip';
import SessionAdvisorPanel from '@/components/features/copilot/SessionAdvisorPanel';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { AdaptiveScheduler } from '@/store/chat/adaptiveScheduler';
import PendingMemoryBadge from '@/components/features/memory/pending/PendingMemoryBadge';
import PendingMemoryDialog from '@/components/features/memory/pending/PendingMemoryDialog';
import { useMemoryStore } from '@/store/memory';
import { fetchPendingApprovals } from '@/hooks/approval/usePendingApprovalsRecovery';
import useApprovalStore from '@/store/useApprovalStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import type { AgentStreamEvent, ChatState } from '@/store/chat/types';
import type { StreamHandlerActions, StreamHandlerState, StreamMutableState } from '@/store/chat/messageStreamHandler';
import Chat from './Chat';
import ExecutionTraceTimeline from '@/components/features/settings/sections/system/ExecutionTraceTimeline';
import { MessageSquare, Activity } from 'lucide-react';

const ArtifactPortal = dynamic(() => import('../artifacts/ArtifactPortal'), {
  ssr: false,
});

interface ErrorViewProps {
  message: string;
}

const ErrorView = memo<ErrorViewProps>(({ message }) => (
  <div className="relative">
    <div className="absolute w-full flex flex-row items-center justify-end mr-5 mt-5">
      <Link href="/settings">
        <Settings className="cursor-pointer lg:hidden" />
      </Link>
    </div>
    <div className="flex flex-col items-center justify-center min-h-screen">
      <p className="dark:text-white/70 text-black/70 text-sm">{message}</p>
    </div>
  </div>
));
ErrorView.displayName = 'ErrorView';

interface AsyncAgentStreamChunkDetail {
  session_id: string;
  chunk: AgentStreamEvent;
}

interface ChatWindowProps {
  id?: string;
}

function isChatRouteHydratedForId(chatId: string | undefined): boolean {
  if (!chatId) {
    return false;
  }
  const state = useChatStore.getState();
  return (
    state.chatId === chatId &&
    state.isMessagesLoaded &&
    (state.messages.length > 0 || Boolean(state.compactedSummary?.trim()))
  );
}

function subscribeChatRouteHydrated(chatId: string | undefined, onStoreChange: () => void): () => void {
  if (!chatId) {
    return () => {};
  }
  return useChatStore.subscribe((state, prevState) => {
    const nextReady = isChatRouteHydratedForId(chatId);
    const prevReady =
      prevState.chatId === chatId &&
      prevState.isMessagesLoaded &&
      (prevState.messages.length > 0 || Boolean(prevState.compactedSummary?.trim()));
    if (nextReady !== prevReady) {
      onStoreChange();
    }
  });
}

const ChatWindow = ({ id }: ChatWindowProps) => {
  const searchParams = useSearchParams();
  const router = useRouter();
  const t = useTranslations('agent');
  const commonT = useTranslations('common');
  const sessionAnalyticsT = useTranslations('settings.sessionAnalytics');
  const snapshotT = useTranslations('chat.snapshot');
  const agentIdFromUrl = searchParams.get('agent_id') ?? searchParams.get('agentId');
  const restoreArgFromUrl = searchParams.get('restore_arg');
  const approvalIdFromUrl = searchParams.get('approval');
  const hasAppliedAgentRef = useRef<string | null>(null);
  const hasAppliedRestoreArgRef = useRef<string | null>(null);
  const hasAppliedApprovalRef = useRef<string | null>(null);
  const isGoalsEnabled = useFeatureGateStore((s) => s.isEnabled('goals_system'));
  const sendMessage = useChatStore((s) => s.sendMessage);
  const [advisorOpen, setAdvisorOpen] = useState(false);
  const [advisorQuestion, setAdvisorQuestion] = useState('');
  const [advisorSelection, setAdvisorSelection] = useState<string | undefined>();
  const [routeHydrationEpoch, setRouteHydrationEpoch] = useState(0);

  useEffect(() => {
    if (!id) {
      return;
    }
    return useChatStore.subscribe((state) => {
      if (
        state.chatId === id &&
        state.isMessagesLoaded &&
        (state.messages.length > 0 || Boolean(state.compactedSummary?.trim()))
      ) {
        setRouteHydrationEpoch((epoch) => epoch + 1);
      }
    });
  }, [id]);

  useEffect(() => {
    if (!id) {
      return;
    }
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ chatId?: string }>).detail;
      if (detail?.chatId !== id) {
        return;
      }
      setRouteHydrationEpoch((epoch) => epoch + 1);
    };
    window.addEventListener('myrm-e2e-chat-route-hydrated', handler);
    return () => window.removeEventListener('myrm-e2e-chat-route-hydrated', handler);
  }, [id]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ question?: string; selection?: string }>).detail;
      setAdvisorQuestion(detail?.question ?? '');
      setAdvisorSelection(detail?.selection);
      setAdvisorOpen(true);
    };
    window.addEventListener('copilot-open-advisor', handler);
    return () => window.removeEventListener('copilot-open-advisor', handler);
  }, []);

  const {
    messages,
    compactedSummary,
    chatId: storeChatId,
    loading,
    messageAppeared,
    notFound,
    loadError,
    initializeChat,
    isMessagesLoaded,
    setActionMode,
    setAgentConfig,
    setInputMessage,
    setPendingArchiveRestoreActions,
    agentConfig,
  } = useChatStore(
    useShallow((state) => ({
      messages: state.messages,
      compactedSummary: state.compactedSummary,
      chatId: state.chatId,
      loading: state.loading,
      messageAppeared: state.messageAppeared,
      notFound: state.notFound,
      loadError: state.loadError,
      initializeChat: state.initializeChat,
      isMessagesLoaded: state.isMessagesLoaded,
      setActionMode: state.setActionMode,
      setAgentConfig: state.setAgentConfig,
      setInputMessage: state.setInputMessage,
      setPendingArchiveRestoreActions: state.setPendingArchiveRestoreActions,
      agentConfig: state.agentConfig,
    })),
  );

  const chatRouteHydratedFromSelector =
    Boolean(id) && storeChatId === id && isMessagesLoaded && (messages.length > 0 || Boolean(compactedSummary?.trim()));

  const chatRouteHydratedDirect = Boolean(id) && isChatRouteHydratedForId(id);

  const chatRouteHydratedSync = useSyncExternalStore(
    (onStoreChange) => subscribeChatRouteHydrated(id, onStoreChange),
    () => isChatRouteHydratedForId(id),
    () => false,
  );

  const storeMessageCountDirect =
    id && useChatStore.getState().chatId === id ? useChatStore.getState().messages.length : 0;

  const storeMessageCountSync = useSyncExternalStore(
    (onStoreChange) => useChatStore.subscribe(onStoreChange),
    () => (id && useChatStore.getState().chatId === id ? useChatStore.getState().messages.length : 0),
    () => 0,
  );

  const storeMessagesDirect = id && useChatStore.getState().chatId === id ? useChatStore.getState().messages : [];

  const chatMessagesForRender = messages.length > 0 ? messages : storeMessagesDirect;

  const chatRouteHydrated = chatRouteHydratedFromSelector || chatRouteHydratedSync || chatRouteHydratedDirect;
  const storeMessageCount = Math.max(storeMessageCountSync, storeMessageCountDirect);
  void routeHydrationEpoch;

  const hasChatContent =
    messages.length > 0 || (Boolean(compactedSummary?.trim()) && Boolean(id) && isMessagesLoaded) || chatRouteHydrated;

  const initConfig = useConfigStore((state) => state.initConfig);
  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);

  useEffect(() => {
    if (!id || !restoreArgFromUrl || !isMessagesLoaded) {
      return;
    }
    const restoreKey = `${id}:${restoreArgFromUrl}`;
    if (hasAppliedRestoreArgRef.current === restoreKey) {
      return;
    }

    hasAppliedRestoreArgRef.current = restoreKey;
    setPendingArchiveRestoreActions([{ type: 'archive_restore', restoreArg: restoreArgFromUrl }]);
    setInputMessage(sessionAnalyticsT('contextHealth.pruning.restorePrompt', { restoreArg: restoreArgFromUrl }));
    router.replace(`/${encodeURIComponent(id)}`, { scroll: false });
    const focusTimer = window.setTimeout(() => {
      if (typeof document === 'undefined') {
        return;
      }
      const inputElement = document.querySelector('textarea');
      if (inputElement instanceof HTMLTextAreaElement) {
        inputElement.focus();
        inputElement.setSelectionRange(inputElement.value.length, inputElement.value.length);
      }
    }, 100);
    return () => {
      window.clearTimeout(focusTimer);
    };
  }, [
    id,
    isMessagesLoaded,
    restoreArgFromUrl,
    router,
    sessionAnalyticsT,
    setInputMessage,
    setPendingArchiveRestoreActions,
  ]);

  useEffect(() => {
    if (!id || !approvalIdFromUrl || !isMessagesLoaded) {
      return;
    }
    const approvalKey = `${id}:${approvalIdFromUrl}`;
    if (hasAppliedApprovalRef.current === approvalKey) {
      return;
    }
    hasAppliedApprovalRef.current = approvalKey;

    void (async () => {
      const approvals = await fetchPendingApprovals();
      const match = approvals.find((approval) => approval.approval_id === approvalIdFromUrl);
      if (match) {
        useApprovalStore.getState().openApproval(match);
      }
      router.replace(`/${encodeURIComponent(id)}`, { scroll: false });
    })();
  }, [approvalIdFromUrl, id, isMessagesLoaded, router]);

  const asyncSchedulerRef = useRef<AdaptiveScheduler | null>(null);
  const pendingInboxRef = useRef<AgentStreamEvent[]>([]);

  useEffect(() => {
    const processInbox = async () => {
      if (pendingInboxRef.current.length === 0) {
        return;
      }
      if (useChatStore.getState().loading) {
        return;
      } // 再次检查确保安全

      const chunk = pendingInboxRef.current.shift();
      if (!chunk) {
        return;
      }
      const { handleMessageStream } = await import('@/store/chat/messageStreamHandler');

      if (!asyncSchedulerRef.current) {
        asyncSchedulerRef.current = new AdaptiveScheduler();
      }

      const store = useChatStore.getState();
      const actions: StreamHandlerActions = {
        setMessages: (updater: (state: StreamMutableState) => void) => {
          store.updateMessages(updater as (state: ChatState) => void);
        },
        setLoading: (loading: boolean) => useChatStore.setState({ loading }),
        setMessageAppeared: (appeared: boolean) => useChatStore.setState({ messageAppeared: appeared }),
        _processSuggestions: store._processSuggestions,
        scheduleAutoSave: store.scheduleAutoSave,
      };

      const stateSnapshot: StreamHandlerState = {
        messages: useChatStore.getState().messages,
        messageAppeared: useChatStore.getState().messageAppeared,
        loading: false, // 只有在不 loading 时才执行
        scheduler: asyncSchedulerRef.current,
      };

      await handleMessageStream(chunk, '', undefined, true, '', stateSnapshot, actions);

      // 处理下一个块
      if (pendingInboxRef.current.length > 0) {
        setTimeout(processInbox, 0);
      }
    };

    const handleAsyncChunk = (e: Event) => {
      const customEvent = e as CustomEvent<AsyncAgentStreamChunkDetail>;
      const { session_id, chunk } = customEvent.detail;

      // 只处理当前会话的流数据
      if (session_id !== id) {
        return;
      }

      const store = useChatStore.getState();

      // 双流防撞锁 (Dual-Stream Collision Lock)
      if (store.loading) {
        // 用户正在对话，放入 Inbox 暂存
        pendingInboxRef.current.push(chunk);
        // 可以增加提示（例如通过 toast 提示）
        return;
      }

      // 如果不 loading，直接放入 Inbox 并开始处理（复用逻辑保证顺序）
      pendingInboxRef.current.push(chunk);
      processInbox();
    };

    // 监听全局的 loading 状态变化，当对话结束（loading 变为 false）时，恢复执行 inbox 中的积压任务
    const unsubscribe = useChatStore.subscribe((state, prevState) => {
      if (prevState.loading === true && state.loading === false) {
        processInbox();
      }
    });

    const handleSystemNotification = (e: Event) => {
      const customEvent = e as CustomEvent<{ data: unknown }>;
      const meta = (customEvent.detail.data as { meta_data?: Record<string, unknown> } | undefined)?.meta_data || {};

      if (meta?.type === 'snapshot_created' && meta?.chat_id === id) {
        toast({
          title: snapshotT('createdTitle'),
          description: (
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-green-500" />
              <span>{snapshotT(`createdMessage.${meta.action ?? 'unknown'}`)}</span>
            </div>
          ),
          variant: 'default',
        });
      }

      if (
        meta?.chat_id === id &&
        (meta?.kind === 'background_job_finish' || meta?.kind === 'voice_background_task_done')
      ) {
        void initializeChat(id);
      }

      if (meta?.kind === 'goal_needs_review' && id && meta?.chat_id === id) {
        void useGoalStore.getState().refreshActiveGoal(id);
      }
    };

    window.addEventListener('async-agent-stream-chunk', handleAsyncChunk);
    window.addEventListener('system-notification', handleSystemNotification);

    return () => {
      window.removeEventListener('async-agent-stream-chunk', handleAsyncChunk);
      window.removeEventListener('system-notification', handleSystemNotification);
      unsubscribe();
    };
  }, [id, initializeChat]);

  useEffect(() => {
    initConfig();
  }, [initConfig]);

  useLayoutEffect(() => {
    initializeChat(id);
  }, [id, initializeChat]);

  // 处理 agent_id URL 参数 - 自动切换到智能代理模式并应用智能体配置
  useEffect(() => {
    if (!agentIdFromUrl) {
      return;
    }
    // 避免重复应用同一个智能体
    if (hasAppliedAgentRef.current === agentIdFromUrl) {
      return;
    }

    const applyAgentConfig = async () => {
      try {
        const agent = await getAgent(agentIdFromUrl);
        if (agent) {
          const currentChatId = useChatStore.getState().chatId;
          if (id && currentChatId && currentChatId !== id) {
            return;
          }
          const { fetchMarketSkills, fetchLocalSkills } = useSkillStore.getState();
          await Promise.all([fetchMarketSkills(true), fetchLocalSkills()]);
          const skillStore = useSkillStore.getState();
          const allSkills = [...skillStore.marketSkills, ...skillStore.localSkills];
          // 校验智能体依赖
          const validation = validateAgentDependencies(agent, allSkills, mcpConfigs);
          if (!validation.isValid) {
            const missingParts = buildMissingDependenciesParts(validation);
            const partsText = missingParts.map((p) => t(p.key, { count: p.count })).join('、');
            toast({
              title: t('validation.dependencyInvalid'),
              description: `${partsText}。${t('validation.pleaseEdit')}`,
              variant: 'destructive',
            });
          }

          // 切换到智能代理模式
          setActionMode('agent');

          // 应用智能体配置
          const config: AgentConfig = {
            selectedSkillIds: agent.skill_ids || [],
            skillConfigs: agent.skill_configs || {},
            selectedMcpNames: agent.mcp_ids || [],
            systemPrompt: agent.system_prompt || '',
            useGlobalInstruction: true,
            autoRestoreDomains: agent.auto_restore_domains || [],
            agentId: agent.id,
            agentName: agent.name,
            agentDescription: agent.description || '',
            avatarUrl: agent.avatar_url,
            suggestionPrompts: agent.suggestion_prompts || undefined,
            memoryDecayProfile: agent.memory_decay_profile || 'normal',
            memoryExtractionPreset: agent.memory_extraction_preset || 'auto',
            browserSource: agent.browser_source || undefined,
            promptMode: agent.prompt_mode || undefined,
            defaultSecurityPreset: agent.default_security_preset ?? undefined,
          };
          setAgentConfig(config);

          // 标记已应用
          hasAppliedAgentRef.current = agentIdFromUrl;

          // 清除 URL 参数，避免刷新时重复应用（保留当前会话路由）
          const nextPath = id ? `/${encodeURIComponent(id)}` : '/';
          router.replace(nextPath, { scroll: false });
        }
      } catch (error) {
        console.warn('加载智能体配置失败:', error);
      }
    };

    applyAgentConfig();
  }, [agentIdFromUrl, id, setActionMode, setAgentConfig, router, mcpConfigs, t]);

  const handleInspectorInstruction = useCallback(
    (instruction: string, refId: string | null) => {
      const formattedInstruction = refId
        ? `[Browser Inspector] 我选中了页面元素 [ref=${refId}]，${instruction || '请对此元素执行操作'}`
        : `[Browser Inspector] ${instruction}`;
      sendMessage(formattedInstruction);
    },
    [sendMessage],
  );

  const handleDesktopInspectorInstruction = useCallback(
    (instruction: string, refId: string | null) => {
      const formattedInstruction = refId
        ? `[Desktop Inspector] 我选中了桌面元素 [@${refId}]，${instruction || '请对此元素执行操作'}`
        : `[Desktop Inspector] ${instruction}`;
      sendMessage(formattedInstruction);
    },
    [sendMessage],
  );

  const pendingMemories = useMemoryStore((s) => s.pendingMemories);
  const pendingCount = useMemoryStore((s) => s.pendingCount);
  const openConfirmDialog = useMemoryStore((s) => s.openConfirmDialog);
  const memoryT = useTranslations('memory');

  const [activeTab, setActiveTab] = useState<'chat' | 'trace'>('chat');
  const recoveryT = useTranslations('recovery');
  useEffect(() => {
    const prev = prevPendingCountRef.current;
    prevPendingCountRef.current = pendingCount;
    // prev === -1 表示首次加载，不触发 toast（避免页面刷新时已有 pending 也弹 toast）
    if (prev >= 0 && pendingCount > prev) {
      const added = pendingCount - prev;
      toast({
        title: memoryT('pendingToast.title'),
        description: memoryT('pendingToast.description', { count: added }),
        duration: 4000,
      });
    }
  }, [pendingCount, memoryT]);

  const handlePendingMemoryClick = useCallback(() => {
    if (pendingMemories.length > 0) {
      openConfirmDialog(pendingMemories[0]);
    }
  }, [pendingMemories, openConfirmDialog]);

  if (notFound) {
    return <NextError statusCode={404} />;
  }

  if (loadError) {
    return <ErrorView message={commonT('connectionFailed')} />;
  }

  const showChatRouteLayout = Boolean(id) || hasChatContent;

  if (showChatRouteLayout) {
    return (
      <>
        {/* CLI Agent 权限对话框 */}
        <PermissionDialog />
        <ToolApprovalDialog />
        <ToolApprovalExpiryWatcher />
        <PendingMemoryDialog />

        <div className="flex h-full w-full">
          <div className="flex-1 min-w-0 flex flex-col">
            {/* Agent Info Banner */}
            {agentConfig?.agentId && <AgentInfoBanner agentId={agentConfig.agentId} />}
            {id ? (
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 border-b border-border/30 bg-muted/20">
                <div className="flex flex-wrap items-center gap-2">
                  <ParentChatLink chatId={id} />
                  <ChatCronLink chatId={id} />
                  <SessionRevertButton sessionId={id} />
                </div>
                {/* 活跃会话 双 Tab 切换器 */}
                <div className="inline-flex items-center rounded-lg bg-muted/60 p-0.5 text-xs font-medium border border-border/40">
                  <button
                    type="button"
                    onClick={() => setActiveTab('chat')}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all ${
                      activeTab === 'chat'
                        ? 'bg-background text-foreground shadow-xs font-semibold'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <MessageSquare className="h-3.5 w-3.5" />
                    <span>{recoveryT('dualTabChat')}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab('trace')}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all ${
                      activeTab === 'trace'
                        ? 'bg-background text-foreground shadow-xs font-semibold'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Activity className="h-3.5 w-3.5 text-amber-500" />
                    <span>{recoveryT('dualTabTrace')}</span>
                  </button>
                </div>
              </div>
            ) : null}
            <WorkingStateBadge />
            {id ? <RunStatusChip chatId={id} /> : null}
            <YoloModeBanner />
            <EStopBanner />
            <ExtensionDisconnectedBanner />
            <ExtensionTakeoverBanner />
            <MemoryRecallDegradedBanner
              compact
              dismissStorageKey={id ? `memory-recall-degraded:${id}` : undefined}
              className="mx-1 mb-1"
            />

            {/* 待审批记忆徽章 */}
            <PendingMemoryBadge
              onClick={handlePendingMemoryClick}
              className="fixed top-3 right-14 z-40 max-sm:top-2 max-sm:right-12"
            />

            {/* 聊天内容或物理执行轨迹：按 activeTab 无缝切换 */}
            <div className="relative flex-1 min-h-0">
              {activeTab === 'chat' ? (
                <>
                  {id && !chatRouteHydrated ? (
                    <div className="absolute inset-0 z-10 bg-background">
                      <MessageListSkeleton />
                    </div>
                  ) : null}
                  <div
                    className="flex h-full min-h-0"
                    key={`${id ?? 'home'}-${routeHydrationEpoch}-${storeMessageCount}-${chatRouteHydrated ? 'hydrated' : 'pending'}`}
                  >
                    <Chat
                      loading={loading}
                      messageAppeared={messageAppeared}
                      messagesOverride={chatMessagesForRender.length > messages.length ? chatMessagesForRender : undefined}
                    />
                  </div>
                </>
              ) : (
                <div className="h-full overflow-y-auto p-4 bg-background">
                  {id && <ExecutionTraceTimeline sessionId={id} pollMs={loading ? 2000 : undefined} />}
                </div>
              )}
            </div>
          </div>

          <ArtifactPortal />
        </div>

        <ChatWindowSatellites
          chatId={id}
          onInspectorInstruction={handleInspectorInstruction}
          onDesktopInspectorInstruction={handleDesktopInspectorInstruction}
        />
        {isGoalsEnabled ? <GoalStatusCard /> : null}
        {id ? (
          <SessionAdvisorPanel
            chatId={id}
            open={advisorOpen}
            onOpenChange={(open) => {
              setAdvisorOpen(open);
              if (!open) {
                setAdvisorQuestion('');
                setAdvisorSelection(undefined);
              }
            }}
            initialQuestion={advisorQuestion}
            selectionSnippet={advisorSelection}
          />
        ) : null}
        <LifeStatusCapsule currentSessionId={id || null} />
      </>
    );
  }

  return (
    <>
      {/* CLI Agent 权限对话框 */}
      <PermissionDialog />
      <ToolApprovalDialog />
      <ToolApprovalExpiryWatcher />
      <YoloModeBanner />
      <EStopBanner />
      <ExtensionDisconnectedBanner />
      <ExtensionTakeoverBanner />
      <MemoryRecallDegradedBanner compact className="mx-2 mt-2" />
      <div className="flex h-full w-full">
        <div className="flex-1 min-w-0 min-h-0">
          <EmptyChat />
        </div>
        {isGoalsEnabled ? (
          <div className="hidden lg:flex h-full shrink-0">
            <GoalControlPlane />
          </div>
        ) : null}
      </div>
      <ChatWindowSatellites
        chatId={id}
        onInspectorInstruction={handleInspectorInstruction}
        onDesktopInspectorInstruction={handleDesktopInspectorInstruction}
      />
      {isGoalsEnabled ? <GoalStatusCard /> : null}
      <LifeStatusCapsule currentSessionId={id || null} />
    </>
  );
};

export default ChatWindow;
