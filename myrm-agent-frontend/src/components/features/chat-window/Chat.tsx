/**
 * 聊天组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md（如有）
 *
 * [INPUT]
 * - @/store/useChatStore (POS: 聊天状态管理)
 * - ./VirtualMessageList (POS: 虚拟滚动消息列表)
 * - ../message-box/MessageBox (POS: 消息展示组件)
 * - ./ConversationJumpBar (POS: 长对话快速定位导航)
 * - ./approval/VisualApprovalAttentionBar (POS: 滚动区外 inline 审批可达条)
 * - ./ScrollToBottomButton (POS: 滚动到底部按钮 + 新消息提示)
 *
 * [OUTPUT]
 * - Chat: 聊天主组件
 *   - 支持虚拟滚动（ENABLE_VIRTUAL_SCROLL 开关）
 *   - 消息列表渲染
 *   - ScrollToBottomButton（滚动到底部 + 新消息提示）
 *   - VisualApprovalAttentionBar（输入框上方 pending 条）
 *   - 输入框
 *   - 智能体配置面板
 *   - 长对话导航（PC dot 导航 + 移动端 Sheet）
 *
 * [POS]
 * 聊天主组件。负责渲染消息列表、输入框、智能体配置面板。
 * 支持两种渲染模式：传统渲染和虚拟滚动渲染。
 * 虚拟滚动模式在长对话场景下提供更好的性能。
 */

'use client';

import { Fragment, useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import MessageInput from './MessageInput';
import CompanionWidget from '../companion/CompanionWidget';
import MessageBox from '../message-box/MessageBox';
import MessageBoxLoading from '../message-box/MessageBoxLoading';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import React from 'react';
import { isNearBottom } from '@/lib/utils/domUtils';
import { stripDatetimeTag } from '@/lib/utils/messageUtils';
import AgentConfigPanel from './agent-config-panel/AgentConfigPanel';
import { useScrollPositionRestore } from '@/hooks/useScrollPositionRestore';
import { VirtualMessageList } from './virtual-message-list';
import { useConfigErrorDetector } from '@/hooks/useConfigErrorDetector';
import ProviderConfigErrorDialog from '@/components/error-boundary/ProviderConfigErrorDialog';
import { CompactedSummaryView } from './CompactedSummaryView';
import { GoalControlPlane } from './goals/GoalControlPlane';
import SessionAnalyticsDialog from '@/components/features/settings/sections/system/SessionAnalyticsDialog';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { ConversationJumpBar, MobileJumpBarSheet } from './ConversationJumpBar';
import { ListTree } from 'lucide-react';
import { useTranslations } from 'next-intl';
import AgentWorkMap from './AgentWorkMap';
import VisualApprovalAttentionBar from './approval/VisualApprovalAttentionBar';
import VisualApprovalOsOverlaySync from './VisualApprovalOsOverlaySync';
import ScrollToBottomButton from './ScrollToBottomButton';

/**
 * 虚拟滚动开关
 *
 * true: 使用虚拟滚动（推荐，长对话性能更好）
 * false: 使用传统渲染（兼容模式）
 *
 * 注意：虚拟滚动模式下，滚动容器是组件内部的 div，
 * 而非 window，滚动行为略有不同。
 */
const ENABLE_VIRTUAL_SCROLL = true;

/** 消息数量阈值，超过此值自动启用虚拟滚动 */
const VIRTUAL_SCROLL_THRESHOLD = 20;

const Chat = ({ loading, messageAppeared }: { loading: boolean; messageAppeared: boolean }) => {
  const t = useTranslations('chat.jumpBar');
  const tMeta = useTranslations('metadata');
  const messageEnd = useRef<HTMLDivElement | null>(null);
  const lastScrollPositionRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputContainerRef = useRef<HTMLDivElement>(null);
  const [showInput, setShowInput] = useState(true);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const virtualScrollToBottomRef = useRef<(() => void) | null>(null);

  const {
    messages: rawMessages,
    chatId,
    compactedSummary,
    activeSessionAnalyticsId,
    setActiveSessionAnalyticsId,
    setActiveSessionAnalyticsMessageId,
  } = useChatStore(
    useShallow((state) => ({
      messages: state.messages,
      chatId: state.chatId,
      compactedSummary: state.compactedSummary,
      activeSessionAnalyticsId: state.activeSessionAnalyticsId,
      setActiveSessionAnalyticsId: state.setActiveSessionAnalyticsId,
      setActiveSessionAnalyticsMessageId: state.setActiveSessionAnalyticsMessageId,
    })),
  );

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

  const { configError, clearConfigError } = useConfigErrorDetector();
  const isGoalsEnabled = useFeatureGateStore((s) => s.isEnabled('goals_system'));

  // JumpBar：虚拟滚动模式的跳转函数引用
  const scrollToMessageRef = useRef<((index: number) => void) | null>(null);

  // 使用滚动位置保存/恢复 Hook
  const { saveScrollPosition, restoreScrollPosition, userScrolledRef, saveTimerRef } = useScrollPositionRestore({
    id: chatId,
    enabled: true,
  });

  const handleJumpToMessage = useCallback(
    (messageIndex: number) => {
      // 虚拟滚动模式：通过 ref 调用 virtualizer.scrollToIndex
      if (scrollToMessageRef.current) {
        scrollToMessageRef.current(messageIndex);
        return;
      }
      // 传统渲染模式：通过 data-message-id 定位 DOM
      const msg = messages[messageIndex];
      if (!msg) return;
      const el = containerRef.current?.querySelector(`[data-message-id="${CSS.escape(String(msg.messageId))}"]`);
      if (el) {
        userScrolledRef.current = true;
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    },
    [messages, userScrolledRef],
  );

  // VirtualMessageList 滚动状态变化回调
  const handleVirtualScrollStateChange = useCallback((scrolledUp: boolean) => {
    setIsUserScrolledUp(scrolledUp);
    if (!scrolledUp) setHasNewMessage(false);
  }, []);

  // ScrollToBottomButton 点击回调
  const handleScrollToBottomClick = useCallback(() => {
    // 虚拟滚动模式
    if (virtualScrollToBottomRef.current) {
      virtualScrollToBottomRef.current();
      setIsUserScrolledUp(false);
      setHasNewMessage(false);
      return;
    }
    // 传统渲染模式
    userScrolledRef.current = false;
    setIsUserScrolledUp(false);
    setHasNewMessage(false);
    if (messageEnd.current) {
      messageEnd.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    setShowInput(true);
  }, [userScrolledRef]);

  // 立即滚动函数，完全无延迟
  const scrollToBottom = useCallback(() => {
    if (!messageEnd.current || userScrolledRef.current) return;

    messageEnd.current.scrollIntoView({
      behavior: 'smooth',
      block: 'end',
    });
    setShowInput(true);
  }, [userScrolledRef]);

  // 聊天切换时重置滚动状态
  useEffect(() => {
    setIsUserScrolledUp(false);
    setHasNewMessage(false);
  }, [chatId]);

  // 组件挂载时恢复滚动位置
  useEffect(() => {
    if (messages.length > 0) {
      const timer = setTimeout(restoreScrollPosition, 100);
      return () => clearTimeout(timer);
    }
  }, [messages.length, restoreScrollPosition, chatId]);

  // 计算消息内容的哈希值，用于检测消息内容变化
  const messagesContentHash = useMemo(() => {
    return messages.map((m) => `${m.messageId}:${m.content?.length || 0}`).join('|');
  }, [messages]);

  const messageBoxElements = useMemo(() => {
    const elements = messages.map((msg, i) => {
      if (msg.isCompactedSummaryView) {
        return (
          <Fragment key={`${msg.messageId}-${i}`}>
            <div data-message-id={msg.messageId}>
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
  }, [messages, loading, messagesContentHash, highlightMessageId]);

  useEffect(() => {
    if (!highlightMessageId || messages.length === 0) return;
    const el = containerRef.current?.querySelector(`[data-message-id="${CSS.escape(highlightMessageId)}"]`);
    if (el) {
      requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    }
  }, [highlightMessageId, messages]);

  const inputElement = useMemo(() => {
    return (
      <div
        ref={inputContainerRef}
        className={`fixed myrm-safe-bottom-floating left-0 right-0 z-40 transition-all duration-300 ${!showInput ? 'opacity-0 translate-y-10' : 'opacity-100'}`}
        style={{
          paddingLeft: 'var(--main-padding-left, 0)',
        }}
      >
        <div className="mx-auto max-w-6xl w-full px-4 space-y-4" style={{ width: 'var(--message-input-width, 820px)' }}>
          <VisualApprovalOsOverlaySync />
          <VisualApprovalAttentionBar messages={messages} onJumpToMessage={handleJumpToMessage} />
          <AgentWorkMap />
          <div className="flex items-end gap-2">
            <CompanionWidget />
            <div className="flex-1 min-w-0">
              <MessageInput key={chatId} loading={loading} />
            </div>
          </div>
          {/* 智能体配置面板 - 仅在智能代理模式下显示，隐藏已保存智能体画廊 */}
          <AgentConfigPanel hideGallery showInkBackground={false} />
        </div>
      </div>
    );
  }, [loading, showInput, chatId, messages, handleJumpToMessage]);

  // 处理滚动事件（合并输入框显示/隐藏逻辑和滚动位置保存逻辑）
  useEffect(() => {
    // 初始化上次滚动位置
    lastScrollPositionRef.current = window.scrollY;

    const handleScroll = () => {
      const currentScrollPosition = window.scrollY;
      const scrollDelta = currentScrollPosition - lastScrollPositionRef.current;

      // 如果向上滚动（scrollDelta < 0）且滚动量超过阈值
      if (scrollDelta < -5) {
        if (!userScrolledRef.current) {
          userScrolledRef.current = true;
          setIsUserScrolledUp(true);
        }
        setShowInput(false);
      }

      // 向下滚动并且滚动到底部附近，才重置标志
      if (scrollDelta > 5 && isNearBottom()) {
        if (userScrolledRef.current) {
          userScrolledRef.current = false;
          setIsUserScrolledUp(false);
          setHasNewMessage(false);
        }
        setShowInput(true);
      }

      // 任何滚动都重置定时器
      if (scrollTimerRef.current) {
        clearTimeout(scrollTimerRef.current);
      }

      // 滚动停止一段时间后显示输入框
      scrollTimerRef.current = setTimeout(() => {
        setShowInput(true);
      }, 1500);

      // 使用防抖保存滚动位置（使用 hook 提供的定时器引用）
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
      saveTimerRef.current = setTimeout(() => {
        saveScrollPosition();
      }, 200);

      // 更新上次滚动位置
      lastScrollPositionRef.current = currentScrollPosition;
    };

    // 监听 window 滚动事件
    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (scrollTimerRef.current) {
        clearTimeout(scrollTimerRef.current);
      }
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, [saveScrollPosition, userScrolledRef, saveTimerRef]);

  // 存储 loading 状态的 ref，用于 ResizeObserver 内部判断
  const loadingRef = useRef(loading);
  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  // 监听容器大小变化，用于处理内容突然增加的情况
  // 仅在 loading 状态下才自动滚动，避免用户手动展开/折叠时触发
  useEffect(() => {
    if (!containerRef.current) return;

    resizeObserverRef.current = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const currentHeight = entry.contentRect.height;
        // 仅在 loading 状态下且用户未滚动时才自动滚动
        if (currentHeight > 0 && !userScrolledRef.current && loadingRef.current) {
          requestAnimationFrame(() => {
            scrollToBottom();
          });
        }
      }
    });

    resizeObserverRef.current.observe(containerRef.current);

    return () => {
      resizeObserverRef.current?.disconnect();
    };
  }, [scrollToBottom, userScrolledRef]);

  // 流式消息更新的滚动处理
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];

    // 监听消息内容变化，处理自动滚动
    if (lastMessage?.role === 'assistant' && loading) {
      if (userScrolledRef.current) {
        setHasNewMessage(true);
      }
      scrollToBottom();
    }

    // 当用户发送消息时，滚动到消息底部
    if (messages[messages.length - 1]?.role === 'user') {
      userScrolledRef.current = false;
      setIsUserScrolledUp(false);
      setHasNewMessage(false);
      scrollToBottom();
    }

    if (messages.length === 1) {
      const cleanContent = stripDatetimeTag(messages[0].content);
      document.title = `${cleanContent.substring(0, 30)} - ${tMeta('appTitle')}`;
    }
  }, [messages, loading, scrollToBottom, userScrolledRef, tMeta]);

  // 更新输入框宽度
  useEffect(() => {
    let resizeTimer: ReturnType<typeof setTimeout> | null = null;

    const updateContainerWidth = () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (containerRef.current) {
          document.documentElement.style.setProperty(
            '--message-input-width',
            `${containerRef.current.scrollWidth || 740}px`,
          );
        }
      }, 100);
    };

    updateContainerWidth();
    window.addEventListener('resize', updateContainerWidth);
    return () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      window.removeEventListener('resize', updateContainerWidth);
    };
  }, [containerRef]);

  // 移动端 JumpBar 触发按钮
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

  // 决定是否使用虚拟滚动
  const useVirtualScroll = ENABLE_VIRTUAL_SCROLL && messages.length > VIRTUAL_SCROLL_THRESHOLD;

  // 虚拟滚动模式
  if (useVirtualScroll) {
    return (
      <div className="flex h-full w-full">
        <div className="flex-1 overflow-hidden">
          <div ref={containerRef} className="flex flex-col h-full relative">
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
            {inputElement}
            <ScrollToBottomButton
              visible={isUserScrolledUp}
              hasNewMessage={hasNewMessage}
              onClick={handleScrollToBottomClick}
            />
          </div>
          <ConversationJumpBar
            messages={messages}
            onJump={handleJumpToMessage}
            loading={loading}
            hasGoalPanel={isGoalsEnabled}
          />
          <MobileJumpBarSheet messages={messages} onJump={handleJumpToMessage} trigger={mobileJumpTrigger} />
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
        </div>
        {isGoalsEnabled && (
          <div className="hidden lg:flex h-full shrink-0">
            <GoalControlPlane />
          </div>
        )}
      </div>
    );
  }

  // 传统渲染模式
  return (
    <div className="flex h-full w-full">
      <div className="flex-1 overflow-hidden overflow-y-auto">
        <div ref={containerRef} className="flex flex-col mx-auto max-w-5xl px-4 md:px-0 relative">
          {messageBoxElements}
          {loading && !messageAppeared && <MessageBoxLoading />}
          {/* 底部填充空间，避免内容被输入框遮挡 */}
          <div className="h-40 lg:h-[15rem] w-full" />
          <div ref={messageEnd} className="h-0" data-message-end="true" />
          {inputElement}
          <ScrollToBottomButton
            visible={isUserScrolledUp}
            hasNewMessage={hasNewMessage}
            onClick={handleScrollToBottomClick}
          />
        </div>
        <ConversationJumpBar
          messages={messages}
          onJump={handleJumpToMessage}
          loading={loading}
          hasGoalPanel={isGoalsEnabled}
        />
        <MobileJumpBarSheet messages={messages} onJump={handleJumpToMessage} trigger={mobileJumpTrigger} />
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
