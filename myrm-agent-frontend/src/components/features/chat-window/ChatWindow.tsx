'use client';

import { useEffect, memo, useRef, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Chat from './Chat';
import EmptyChat from './EmptyChat';
import MessageListSkeleton from './MessageListSkeleton';
import { Settings, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import NextError from 'next/error';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import ArtifactPortal from '../artifacts/ArtifactPortal';
import { getAgent } from '@/services/agent';
import { AgentConfig } from '@/store/chat/types';
import { useSkillStore } from '@/store/skill';
import { validateAgentDependencies, buildMissingDependenciesParts } from '@/lib/utils/agentConfigValidator';
import { toast } from '@/hooks/useToast';
import { useTranslations } from 'next-intl';
import { PermissionDialog } from '@/components/features/cli-agent/PermissionDialog';
import ToolApprovalDialog from './ToolApprovalDialog';
import ToolApprovalExpiryWatcher from './ToolApprovalExpiryWatcher';
import AgentInfoBanner from './AgentInfoBanner';
import YoloModeBanner from './YoloModeBanner';
import EStopBanner from './EStopBanner';
import ExtensionDisconnectedBanner from './ExtensionDisconnectedBanner';
import SubagentPromptButton from './SubagentPromptButton';
import SubagentDashboard from './SubagentDashboard';
import { VisualDesktopToggle } from '@/components/features/app-shell/VisualDesktopToggle';
import { BrowserLiveView, BrowserInspectorToggle } from '@/components/features/browser-inspector';
import { BrowserRecordingToggle, BrowserRecordingPanel } from '@/components/features/browser-recording';
import { DesktopLiveView, DesktopInspectorToggle } from '@/components/features/desktop-inspector';
import { FileSnapshotPanel } from '@/components/features/checkpoint';
import SessionRevertButton from '@/components/features/message-actions/SessionRevertButton';
import { LifeStatusCapsule } from './LifeStatusCapsule';
import PetOverlay from '../companion/sprite/PetOverlay';
import { GoalStatusCard } from './goals/GoalStatusCard';
import { GoalControlPlane } from './goals/GoalControlPlane';
import { ParentChatLink } from './ParentChatLink';
import WorkingStateBadge from './WorkingStateBadge';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { AdaptiveScheduler } from '@/store/chat/adaptiveScheduler';
import { PendingMemoryBadge, PendingMemoryDialog } from '@/components/features/memory';
import { useMemoryStore } from '@/store/memory';
import type { AgentStreamEvent, ChatState } from '@/store/chat/types';
import type { StreamHandlerActions, StreamHandlerState, StreamMutableState } from '@/store/chat/messageStreamHandler';

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

const ChatWindow = ({ id }: ChatWindowProps) => {
  const searchParams = useSearchParams();
  const router = useRouter();
  const t = useTranslations('agent');
  const commonT = useTranslations('common');
  const sessionAnalyticsT = useTranslations('settings.sessionAnalytics');
  const agentIdFromUrl = searchParams.get('agent_id');
  const restoreArgFromUrl = searchParams.get('restore_arg');
  const hasAppliedAgentRef = useRef<string | null>(null);
  const hasAppliedRestoreArgRef = useRef<string | null>(null);
  const isGoalsEnabled = useFeatureGateStore((s) => s.isEnabled('goals_system'));
  const sendMessage = useChatStore((s) => s.sendMessage);

  const {
    messages,
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

  const initConfig = useConfigStore((state) => state.initConfig);
  const mcpConfigs = useConfigStore((state) => state.mcpConfigs);
  const { marketSkills, localSkills } = useSkillStore();

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

  const asyncSchedulerRef = useRef<AdaptiveScheduler | null>(null);
  const pendingInboxRef = useRef<AgentStreamEvent[]>([]);

  useEffect(() => {
    const processInbox = async () => {
      if (pendingInboxRef.current.length === 0) return;
      if (useChatStore.getState().loading) return; // 再次检查确保安全

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
      if (session_id !== id) return;

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
      const customEvent = e as CustomEvent<{ data: any }>;
      const notification = customEvent.detail.data;
      const meta = notification?.meta_data || {};
      
      // We don't have session_id in the global event directly, 
      // but we can assume if the user is in this chat window, the snapshot is relevant
      if (meta?.type === 'snapshot_created') {
        toast({
          title: '系统保护',
          description: (
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-green-500" />
              <span>{notification.message || '正在创建系统快照，保护您的代码'}</span>
            </div>
          ),
          variant: 'default',
        });
      }
    };

    window.addEventListener('async-agent-stream-chunk', handleAsyncChunk);
    window.addEventListener('system-notification', handleSystemNotification);
    
    return () => {
      window.removeEventListener('async-agent-stream-chunk', handleAsyncChunk);
      window.removeEventListener('system-notification', handleSystemNotification);
      unsubscribe();
    };
  }, [id]);

  useEffect(() => {
    initConfig();
  }, [initConfig]);

  useEffect(() => {
    initializeChat(id);
  }, [id, initializeChat]);

  // 处理 agent_id URL 参数 - 自动切换到智能代理模式并应用智能体配置
  useEffect(() => {
    if (!agentIdFromUrl) return;
    // 避免重复应用同一个智能体
    if (hasAppliedAgentRef.current === agentIdFromUrl) return;

    const applyAgentConfig = async () => {
      try {
        const agent = await getAgent(agentIdFromUrl);
        if (agent) {
          // 校验智能体依赖
          const allSkills = [...marketSkills, ...localSkills];
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
            browserSource: agent.browser_source || undefined,
          };
          setAgentConfig(config);

          // 标记已应用
          hasAppliedAgentRef.current = agentIdFromUrl;

          // 清除 URL 参数，避免刷新时重复应用
          router.replace('/', { scroll: false });
        }
      } catch (error) {
        console.warn('加载智能体配置失败:', error);
      }
    };

    applyAgentConfig();
  }, [agentIdFromUrl, setActionMode, setAgentConfig, router, marketSkills, localSkills, mcpConfigs, t]);

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

  const prevPendingCountRef = useRef(-1);
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

  if (!isMessagesLoaded) {
    return (
      <>
        {id ? <SubagentDashboard chatId={id} /> : null}
        <MessageListSkeleton />
      </>
    );
  }

  if (notFound) {
    return <NextError statusCode={404} />;
  }

  if (loadError) {
    return <ErrorView message={commonT('connectionFailed')} />;
  }

  if (messages.length > 0) {
    return (
      <>
        {/* CLI Agent 权限对话框 */}
        <PermissionDialog />
        <ToolApprovalDialog />
        <ToolApprovalExpiryWatcher />
        <PendingMemoryDialog />

        <div className="flex h-full w-full">
          {/* 主内容区域 - 工件弹窗采用 overlay 模式，不挤压聊天空间 */}
          <div className="flex-1 min-w-0 w-full flex flex-col">
            {/* Agent Info Banner */}
            {agentConfig?.agentId && <AgentInfoBanner agentId={agentConfig.agentId} />}
            {id && <ParentChatLink chatId={id} />}
            <WorkingStateBadge />
            <YoloModeBanner />
            <EStopBanner />
            <ExtensionDisconnectedBanner />

            {/* 待审批记忆徽章 */}
            <PendingMemoryBadge
              onClick={handlePendingMemoryClick}
              className="fixed top-3 right-14 z-40 max-sm:top-2 max-sm:right-12"
            />

            {/* 聊天内容 */}
            <div className="flex-1 min-h-0">
              <Chat loading={loading} messageAppeared={messageAppeared} />
            </div>
          </div>

          {/* Artifact Portal 侧边面板 - 完全 overlay 模式 */}
          <ArtifactPortal />
        </div>

        {/* Visual Desktop 直播按钮 */}
        <VisualDesktopToggle />

        {/* Browser Inspector */}
        <BrowserInspectorToggle />
        <BrowserLiveView onSendInstruction={handleInspectorInstruction} />

        {/* Browser Recording */}
        <BrowserRecordingToggle />
        <BrowserRecordingPanel />

        {/* Desktop Inspector */}
        <DesktopInspectorToggle />
        <DesktopLiveView onSendInstruction={handleDesktopInspectorInstruction} />

        {/* File Snapshot Panel + Session Revert */}
        <FileSnapshotPanel />
        {id && (
          <div className="fixed bottom-24 right-[4.5rem] z-50 max-sm:bottom-20 max-sm:right-16 bg-secondary rounded-full shadow-lg">
            <SessionRevertButton sessionId={id} />
          </div>
        )}

        {/* Subagent 智能提示按钮 */}
        <SubagentPromptButton />

        <SubagentDashboard chatId={id} />

        {/* Goal Status Card */}
        {isGoalsEnabled && <GoalStatusCard />}

        {/* Idle Task Status Breathing Light */}
        <LifeStatusCapsule currentSessionId={id || null} />

        {/* Pet Sprite Overlay */}
        <PetOverlay />
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
      <div className="flex h-full w-full">
        <div className="flex-1 min-w-0 min-h-0">
          <EmptyChat />
        </div>
        {isGoalsEnabled && (
          <div className="hidden lg:flex h-full shrink-0">
            <GoalControlPlane />
          </div>
        )}
      </div>
      <SubagentDashboard chatId={id} />
      {isGoalsEnabled && <GoalStatusCard />}
      <LifeStatusCapsule currentSessionId={id || null} />
      <PetOverlay />
    </>
  );
};

export default ChatWindow;
