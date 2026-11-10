'use client';

import { useEffect, useLayoutEffect, memo, useCallback, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import EmptyChat from './EmptyChat';
import MessageListSkeleton from './MessageListSkeleton';
import { Settings } from 'lucide-react';
import Link from 'next/link';
import NextError from 'next/error';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import { usePendingMemoryToast } from '@/hooks/shared/usePendingMemoryToast';
import { useTranslations } from 'next-intl';
import ToolApprovalDialog from './ToolApprovalDialog';
import ToolApprovalExpiryWatcher from './ToolApprovalExpiryWatcher';
import AgentInfoBanner from './AgentInfoBanner';
import YoloModeBanner from './YoloModeBanner';
import EStopBanner from './EStopBanner';
import ExtensionDisconnectedBanner from './ExtensionDisconnectedBanner';
import ExtensionTakeoverBanner from './ExtensionTakeoverBanner';
import WorkspaceTrustBanner from '@/components/features/project-workspace/WorkspaceTrustBanner';
import { useProjectStore } from '@/store/useProjectStore';
import ChatWindowSatellites, { GoalControlPlane, GoalStatusCard, LifeStatusCapsule } from './ChatWindowSatellites';
import { FiveContractDeliveryStatusPanel } from './FiveContractDeliveryStatusPanel';
import { LoopStatusBar } from './LoopStatusBar';
import WorkingStateBadge from './WorkingStateBadge';
import RunStatusChip from '@/components/features/copilot/RunStatusChip';
import SessionAdvisorPanel from '@/components/features/copilot/SessionAdvisorPanel';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import PendingMemoryBadge from '@/components/features/memory/pending/PendingMemoryBadge';
import PendingMemoryDialog from '@/components/features/memory/pending/PendingMemoryDialog';
import MemoryConflictChatBanner from '@/components/features/memory/pending/MemoryConflictChatBanner';
import { useMemoryStore } from '@/store/memory';
import Chat from './Chat';
import ChatSessionHeader, { type ChatWindowTab } from './ChatSessionHeader';
import { useChatRouteHydration } from './useChatRouteHydration';
import { useChatUrlEntries } from './useChatUrlEntries';
import { useAsyncAgentStream } from './useAsyncAgentStream';
import { useChatSystemNotifications } from './useChatSystemNotifications';
import { useSessionAdvisor } from './useSessionAdvisor';
import { useInspectorInstructions } from './useInspectorInstructions';
import { ExtensionUIModal } from '../extension-ui';
import { TaskHudOverlay } from '../task-hud';
import { useExtensionUIStore } from '@/store/useExtensionUIStore';
import ExecutionTraceTimeline from '@/components/features/settings/sections/system/ExecutionTraceTimeline';

const ArtifactPortal = dynamic(() => import('../artifacts/ArtifactPortal'), {
  ssr: false,
  // Skeleton while the portal chunk loads: avoids a silent blank panel under
  // dev-chunk stalls and satisfies the `artifact-loading` E2E contract.
  loading: () => (
    <output data-testid="artifact-loading" aria-busy="true" className="block animate-pulse h-full w-full" />
  ),
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

interface ChatWindowProps {
  id?: string;
}

const ChatWindow = ({ id }: ChatWindowProps) => {
  const router = useRouter();
  const commonT = useTranslations('common');
  const isGoalsEnabled = useFeatureGateStore((s) => s.isEnabled('goals_system'));
  const [activeTab, setActiveTab] = useState<ChatWindowTab>('chat');
  const advisor = useSessionAdvisor();
  const { handleInspectorInstruction, handleDesktopInspectorInstruction } = useInspectorInstructions();
  const { chatMessages, chatMessagesForRender, chatRouteHydrated, routeHydrationEpoch, storeMessageCount } =
    useChatRouteHydration(id);
  useChatUrlEntries(id);
  useAsyncAgentStream(id);
  useChatSystemNotifications(id);

  useEffect(() => {
    useExtensionUIStore.getState().setChatId(id || null);
  }, [id]);

  const { loading, messageAppeared, notFound, loadError, initializeChat, agentConfig } = useChatStore(
    useShallow((state) => ({
      loading: state.loading,
      messageAppeared: state.messageAppeared,
      notFound: state.notFound,
      loadError: state.loadError,
      initializeChat: state.initializeChat,
      agentConfig: state.agentConfig,
    })),
  );

  const activeProjectId = useProjectStore((s) => (typeof s.activeFilter === 'string' ? s.activeFilter : null));
  const activeProject = useProjectStore((s) => s.projects.find((p) => p.id === activeProjectId));
  const activeWorkspacePath = activeProject?.workspacePath || null;

  const initConfig = useConfigStore((state) => state.initConfig);

  useEffect(() => {
    initConfig();
  }, [initConfig]);

  useLayoutEffect(() => {
    // The `/` route mounts this window with no id while the store may already hold the chat to show there — the
    // incognito toggle chooses one before it navigates here. Resetting would replace that id and clear the flag
    // the toggle just set, so the reset is skipped only when there is nothing to replace: an empty, fully loaded
    // chat that no summary stands for and that did not fail to load. A chat with messages (or a compacted one)
    // still starts over, so arriving home from a real conversation opens a new one.
    const current = useChatStore.getState();
    const holdsEmptyChat =
      Boolean(current.chatId) &&
      current.isMessagesLoaded &&
      !current.notFound &&
      !current.loadError &&
      current.messages.length === 0 &&
      !current.compactedSummary?.trim();
    if (id === undefined && holdsEmptyChat) {
      return;
    }
    initializeChat(id);
  }, [id, initializeChat]);

  const pendingMemories = useMemoryStore((s) => s.pendingMemories);
  const conflictCount = useMemoryStore((s) => s.conflictCount);
  const openConfirmDialog = useMemoryStore((s) => s.openConfirmDialog);
  usePendingMemoryToast();

  const handlePendingMemoryClick = useCallback(() => {
    if (conflictCount > 0) {
      router.push('/settings/memory?tab=pending');
      return;
    }
    if (pendingMemories.length > 0) {
      openConfirmDialog(pendingMemories[0]);
    }
  }, [conflictCount, pendingMemories, openConfirmDialog, router]);

  if (notFound) {
    return <NextError statusCode={404} />;
  }

  if (loadError) {
    return <ErrorView message={commonT('connectionFailed')} />;
  }

  // Home turns into the chat layout the moment its first message exists, before the route carries an id.
  const showChatRouteLayout = Boolean(id) || chatMessages.length > 0;

  if (showChatRouteLayout) {
    return (
      <>
        <ToolApprovalDialog />
        <ToolApprovalExpiryWatcher />
        <PendingMemoryDialog />

        <div className="flex h-full w-full">
          <div className="flex-1 min-w-0 flex flex-col">
            {/* Agent Info Banner */}
            {agentConfig?.agentId && <AgentInfoBanner agentId={agentConfig.agentId} />}
            {id ? <ChatSessionHeader chatId={id} activeTab={activeTab} onTabChange={setActiveTab} /> : null}
            <WorkingStateBadge chatId={id} />
            {id ? <RunStatusChip chatId={id} /> : null}
            <YoloModeBanner />
            <EStopBanner />
            <ExtensionDisconnectedBanner />
            <ExtensionTakeoverBanner />
            <WorkspaceTrustBanner workspacePath={activeWorkspacePath} />
            <LoopStatusBar chatId={id} />
            {activeTab === 'chat' ? (
              <MemoryConflictChatBanner chatId={id} className="px-4 shrink-0 max-w-3xl mx-auto w-full" />
            ) : null}

            {/* 五合同交付生命周期进度面板 */}
            {id && activeTab === 'chat' && (
              <div className="px-4 py-1.5 shrink-0 max-w-3xl mx-auto w-full">
                <FiveContractDeliveryStatusPanel chatId={id} />
              </div>
            )}

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
                  <div className="relative flex h-full min-h-0 w-full flex-col overflow-hidden bg-background">
                    <Chat
                      key={`${id ?? 'home'}-${routeHydrationEpoch}-${storeMessageCount}-${chatRouteHydrated ? 'hydrated' : 'pending'}`}
                      loading={loading}
                      messageAppeared={messageAppeared}
                      messagesOverride={
                        chatMessagesForRender.length > chatMessages.length ? chatMessagesForRender : undefined
                      }
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
            open={advisor.open}
            onOpenChange={advisor.onOpenChange}
            initialQuestion={advisor.question}
            selectionSnippet={advisor.selection}
          />
        ) : null}
        <LifeStatusCapsule currentSessionId={id || null} />
        <ExtensionUIModal />
        <TaskHudOverlay />
      </>
    );
  }

  return (
    <>
      <ToolApprovalDialog />
      <ToolApprovalExpiryWatcher />
      {/* AppLayout floats its sidebar toggle over the top-left corner below the desktop breakpoint; the banners keep clear of it. */}
      <div className="max-lg:pl-12">
        <YoloModeBanner />
        <EStopBanner />
        <ExtensionDisconnectedBanner />
        <ExtensionTakeoverBanner />
      </div>
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
      <ExtensionUIModal />
      <TaskHudOverlay />
    </>
  );
};

export default ChatWindow;
