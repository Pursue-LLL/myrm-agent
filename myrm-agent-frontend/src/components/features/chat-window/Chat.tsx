/**
 * 聊天组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md（如有）
 *
 * [INPUT]
 * - @/store/useChatStore (POS: 聊天状态管理)
 * - ./useChatScroll (POS: 滚动控制：跳转 / 自动跟随 / 阅读位置恢复)
 * - ./useMessageInputWidth (POS: 输入框与消息列同宽)
 * - ./virtual-message-list (POS: 虚拟滚动消息列表)
 * - ../message-box/MessageBox (POS: 消息展示组件)
 * - ./TurnTimelineRail (POS: 会话时间线大纲导航导轨)
 * - ./approval/HumanAttentionBar (POS: 输入框上方统一 HITL 条)
 * - ./ScrollToBottomButton (POS: 滚动到底部按钮 + 新消息提示)
 *
 * [OUTPUT]
 * - Chat: 聊天主组件
 *   - 消息列表：超过 20 条自动切换为虚拟滚动，两种模式共用同一棵外壳树
 *   - ScrollToBottomButton（滚动到底部 + 新消息提示）
 *   - HumanAttentionBar（输入框上方统一 HITL 条）
 *   - 输入框
 *   - 智能体配置面板
 *   - 长对话导航（PC dot 导航 + 移动端 Sheet）
 *
 * [POS]
 * 聊天主组件。负责渲染消息列表、输入框、智能体配置面板与各类浮层，滚动行为交给 useChatScroll。
 * 虚拟滚动模式在长对话场景下提供更好的性能，滚动容器是列表内部的 div 而非 window。
 */

'use client';

import React, { Fragment, useEffect, useMemo } from 'react';

import { useSearchParams } from 'next/navigation';
import MessageInput from './MessageInput';
import CompanionWidget from '../companion/CompanionWidget';
import MessageBox from '../message-box/MessageBox';
import MessageBoxLoading from '../message-box/MessageBoxLoading';
import useChatStore from '@/store/useChatStore';
import { useStoreSnapshot } from '@/hooks/shared/useStoreSnapshot';
import { buildMessageRenderFingerprint } from '@/store/chat/messageRenderFingerprint';
import { useShallow } from 'zustand/react/shallow';
import { stripDatetimeTag } from '@/lib/utils/messageUtils';
import AgentConfigPanel from './agent-config-panel/AgentConfigPanel';
import { VirtualMessageList } from './virtual-message-list';
import { useConfigErrorDetector } from '@/hooks/settings/useConfigErrorDetector';
import ProviderConfigErrorDialog from '@/components/error-boundary/ProviderConfigErrorDialog';
import { CompactedSummaryView } from './CompactedSummaryView';
import { GoalControlPlane } from './goals/GoalControlPlane';
import SessionAnalyticsDialog from '@/components/features/settings/sections/system/SessionAnalyticsDialog';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { TurnTimelineRail, MobileTurnOutlineSheet } from './TurnTimelineRail';
import { useComposerFastFocus } from './useComposerFastFocus';
import { ComposerClearanceSpacer } from './ComposerClearanceSpacer';
import { useChatScroll } from './useChatScroll';
import { useMessageInputWidth } from './useMessageInputWidth';
import { ListTree } from 'lucide-react';
import { useTranslations } from 'next-intl';
import HumanAttentionBar from './approval/HumanAttentionBar';
import VisualApprovalOsOverlaySync from './approval/VisualApprovalOsOverlaySync';
import { useRewindStore } from '@/store/chat/useRewindStore';
import { RewindDialog } from './RewindDialog';
import ScrollToBottomButton from './ScrollToBottomButton';
import { UserQuestionNav, UserQuestionOutlineDrawer, useUserQuestionNavStore } from './question-nav';
import type { Message } from '@/store/chat/types/messages';

const EMPTY_MESSAGES: Message[] = [];

/** 消息数量阈值，超过此值自动启用虚拟滚动 */
const VIRTUAL_SCROLL_THRESHOLD = 20;

const Chat = ({
  loading,
  messageAppeared,
  messagesOverride,
}: {
  loading: boolean;
  messageAppeared: boolean;
  messagesOverride?: Message[];
}) => {
  const t = useTranslations('chat.turnRail');
  const tMeta = useTranslations('metadata');

  const {
    chatId,
    compactedSummary,
    turnOutlines,
    loadThroughTurn,
    activeSessionAnalyticsId,
    setActiveSessionAnalyticsId,
    setActiveSessionAnalyticsMessageId,
  } = useChatStore(
    useShallow((state) => ({
      chatId: state.chatId,
      compactedSummary: state.compactedSummary,
      turnOutlines: state.turnOutlines,
      loadThroughTurn: state.loadThroughTurn,
      activeSessionAnalyticsId: state.activeSessionAnalyticsId,
      setActiveSessionAnalyticsId: state.setActiveSessionAnalyticsId,
      setActiveSessionAnalyticsMessageId: state.setActiveSessionAnalyticsMessageId,
    })),
  );

  const rewindTarget = useRewindStore((s) => s.target);
  const closeRewind = useRewindStore((s) => s.closeRewind);

  // 全局 Mod+K / Cmd+K / Ctrl+K / Mod+Shift+C 快速聚焦 Composer
  useComposerFastFocus({ enabled: true });

  // Streaming hot path: the manual subscription (DefaultLane wakeup) is the
  // only messages source. `messages` must NOT be selected via useShallow:
  // its notifications route through useSyncExternalStore (SyncLane) and
  // re-create the nested-update ratchet this hook removes.
  const rawMessagesFromSync = useStoreSnapshot(
    (onStoreChange) => useChatStore.subscribe(onStoreChange),
    () => useChatStore.getState().messages,
    () => EMPTY_MESSAGES,
    chatId,
  );

  const rawMessages = messagesOverride?.length ? messagesOverride : rawMessagesFromSync;

  const messages = useMemo(() => {
    const safeMessages = Array.isArray(rawMessages) ? rawMessages : [];
    if (compactedSummary && safeMessages.length > 0) {
      return [
        {
          messageId: 'compacted-summary-view',
          chatId: chatId || '',
          createdAt: safeMessages[0].createdAt || new Date(),
          content: '',
          role: 'system' as const,
          isCompactedSummaryView: true,
        },
        ...safeMessages,
      ];
    }
    return safeMessages;
  }, [rawMessages, compactedSummary, chatId]);

  const searchParams = useSearchParams();
  const highlightMessageId = searchParams.get('highlight');

  const pendingCount = useUserQuestionNavStore((s) => s.pendingCount);
  const pendingItems = useUserQuestionNavStore((s) => s.pendingItems);
  const syncNavMessages = useUserQuestionNavStore((s) => s.syncMessages);

  useEffect(() => {
    syncNavMessages(messages);
  }, [messages, syncNavMessages]);

  const { configError, clearConfigError } = useConfigErrorDetector();
  const isGoalsEnabled = useFeatureGateStore((s) => s.isEnabled('goals_system'));

  const {
    containerRef,
    messageEnd,
    showInput,
    isUserScrolledUp,
    hasNewMessage,
    userScrolledRef,
    scrollToMessageRef,
    virtualScrollToBottomRef,
    handleJumpToMessage,
    handleJumpToMessageId,
    handleVirtualScrollStateChange,
    handleScrollToBottomClick,
  } = useChatScroll({ chatId, messages, loading, highlightMessageId });

  useMessageInputWidth(containerRef);

  // 首条消息作为页面标题
  useEffect(() => {
    if (messages.length === 1) {
      const cleanContent = stripDatetimeTag(messages[0].content);
      document.title = `${cleanContent.substring(0, 30)} - ${tMeta('appTitle')}`;
    }
  }, [messages, tMeta]);

  // 计算消息内容的哈希值，用于检测消息内容变化
  const messagesContentHash = useMemo(() => buildMessageRenderFingerprint(messages), [messages]);

  // The fingerprint invalidates the memo when message content changes without a new array reference.
  const messageBoxElements = useMemo(() => {
    const elements = messages.map((msg, i) => {
      if (msg.isCompactedSummaryView) {
        return (
          <Fragment key={`${msg.messageId}-${i}`}>
            <div data-message-id={msg.messageId} data-testid="compacted-summary-view">
              <CompactedSummaryView />
            </div>
          </Fragment>
        );
      }

      const isLast = i === messages.length - 1;
      const isHighlighted = !!highlightMessageId && String(msg.messageId) === highlightMessageId;

      return (
        <Fragment key={`${msg.messageId}-${i}`}>
          <div
            data-message-id={msg.messageId}
            className={isHighlighted ? 'ring-2 ring-primary/40 rounded-lg transition-all duration-1000' : undefined}
          >
            <MessageBox message={msg} messageIndex={i} loading={loading} isLast={isLast} />
          </div>
          {!isLast && msg.role === 'assistant' && <div className="h-px w-full bg-secondary" />}
        </Fragment>
      );
    });

    return elements;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, loading, messagesContentHash, highlightMessageId]);

  const inputElement = useMemo(() => {
    return (
      <div
        data-composer-dock
        className={`fixed myrm-safe-bottom-floating left-0 right-0 z-40 transition-all duration-300 ${!showInput ? 'opacity-0 translate-y-10' : 'opacity-100'}`}
        style={{
          paddingLeft: 'var(--main-padding-left, 0)',
        }}
      >
        <div className="mx-auto max-w-6xl w-full px-4 space-y-4" style={{ width: 'var(--message-input-width, 820px)' }}>
          <VisualApprovalOsOverlaySync />
          <HumanAttentionBar messages={messages} onJumpToMessage={handleJumpToMessage} />
          <div className="flex items-end gap-2">
            <CompanionWidget />
            <div className="flex-1 min-w-0">
              <MessageInput key={chatId} loading={loading} />
            </div>
          </div>
          {/* 智能体配置面板 - 仅在智能代理模式下显示 */}
          <AgentConfigPanel />
        </div>
      </div>
    );
  }, [loading, showInput, chatId, messages, handleJumpToMessage]);

  // 移动端大纲抽屉触发按钮
  const mobileJumpTrigger = useMemo(
    () => (
      <button
        className="fixed bottom-24 right-3 z-30 md:hidden
          w-9 h-9 rounded-full bg-secondary/80 backdrop-blur-sm
          border border-border shadow-sm
          flex items-center justify-center
          text-muted-foreground hover:text-foreground
          transition-colors"
        aria-label={t('ariaLabel')}
      >
        <ListTree size={16} />
      </button>
    ),
    [t],
  );

  const jumpToQuestion = (_index: number, messageId: string) => {
    handleJumpToMessageId(messageId);
  };

  const isVirtualList = messages.length > VIRTUAL_SCROLL_THRESHOLD;

  // 两种列表模式共用同一棵外壳树：输入框与浮层在消息数越过阈值时保持挂载
  return (
    <div className="flex h-full w-full">
      <div className={isVirtualList ? 'flex-1 overflow-hidden' : 'flex-1 overflow-hidden overflow-y-auto'}>
        <div
          ref={containerRef}
          className={
            isVirtualList ? 'flex flex-col h-full relative' : 'flex flex-col mx-auto max-w-5xl px-4 md:px-0 relative'
          }
        >
          {isVirtualList ? (
            <VirtualMessageList
              messages={messages}
              loading={loading}
              messageAppeared={messageAppeared}
              userScrolledRef={userScrolledRef}
              containerRef={containerRef}
              chatId={chatId}
              highlightMessageId={highlightMessageId}
              scrollToMessageRef={scrollToMessageRef}
              scrollToBottomRef={virtualScrollToBottomRef}
              onUserScrolledChange={handleVirtualScrollStateChange}
            />
          ) : (
            <>
              {messageBoxElements}
              {loading && !messageAppeared && <MessageBoxLoading />}
              {/* 底部填充空间，避免内容被输入框遮挡；高度随输入框实际高度变化 */}
              <ComposerClearanceSpacer columnRef={containerRef} className="min-h-40 lg:min-h-[15rem] w-full shrink-0" />
              <div ref={messageEnd} className="h-0" data-message-end="true" />
            </>
          )}
          {inputElement}
          <ScrollToBottomButton
            visible={isUserScrolledUp}
            hasNewMessage={hasNewMessage}
            onClick={handleScrollToBottomClick}
            pendingCount={pendingCount}
            pendingItems={pendingItems}
          />
          <UserQuestionNav onJumpToMessageIndex={jumpToQuestion} />
          <UserQuestionOutlineDrawer onJumpToMessageIndex={jumpToQuestion} />
        </div>
        <TurnTimelineRail
          messages={messages}
          turnOutlines={turnOutlines}
          onJump={handleJumpToMessage}
          onJumpToMessageId={handleJumpToMessageId}
          onLoadThroughTurn={loadThroughTurn}
          loading={loading}
          hasGoalPanel={isGoalsEnabled}
        />
        <MobileTurnOutlineSheet
          messages={messages}
          turnOutlines={turnOutlines}
          onJump={handleJumpToMessage}
          onJumpToMessageId={handleJumpToMessageId}
          onLoadThroughTurn={loadThroughTurn}
          trigger={mobileJumpTrigger}
        />
        <ProviderConfigErrorDialog error={configError} onClose={clearConfigError} />
        {activeSessionAnalyticsId && (
          <SessionAnalyticsDialog
            sessionId={activeSessionAnalyticsId}
            onClose={() => {
              setActiveSessionAnalyticsMessageId(null);
              setActiveSessionAnalyticsId(null);
            }}
          />
        )}
        {rewindTarget && (
          <RewindDialog
            open={true}
            onOpenChange={(open) => {
              if (!open) {
                closeRewind();
              }
            }}
            chatId={rewindTarget.chatId}
            messageId={rewindTarget.messageId}
            messageIndex={rewindTarget.messageIndex}
          />
        )}
      </div>
      {isGoalsEnabled && (
        <div className="hidden lg:flex h-full shrink-0">
          <GoalControlPlane />
        </div>
      )}
    </div>
  );
};

export default React.memo(Chat);
