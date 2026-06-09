/**
 * 虚拟消息列表组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - @tanstack/react-virtual::useVirtualizer (POS: 虚拟滚动核心库)
 * - @/store/chat/types::Message (POS: 消息类型定义)
 * - ./MessageRow (POS: 单条消息行组件)
 * - ./useMessageHeights (POS: 消息高度缓存 Hook)
 *
 * [OUTPUT]
 * - VirtualMessageList: 虚拟滚动消息列表组件
 *   - 只渲染可视区域内的消息
 *   - 支持动态高度
 *   - 支持流式更新自动滚动
 *   - 支持向上滚动加载历史
 *   - 支持搜索结果跳转定位和高亮
 *   - 通过 scrollToMessageRef 暴露 scrollToIndex 给外部组件
 *   - 通过 scrollToBottomRef 暴露 scrollToBottom 给外部组件
 *   - 通过 onUserScrolledChange 通知外部滚动状态变化
 *
 * [POS]
 * 高性能虚拟滚动消息列表。替代传统的 messages.map 渲染方式，
 * 无论消息数量多少，DOM 数量保持固定（~10-15 个），确保
 * 长对话场景下的流畅体验。是聊天性能优化的核心组件。
 */

'use client';

import { useRef, useEffect, useCallback, memo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import MessageBox from '../../message-box/MessageBox';
import MessageBoxLoading from '../../message-box/MessageBoxLoading';
import { useMessageHeights } from './useMessageHeights';
import { CompactedSummaryView } from '../CompactedSummaryView';

/** 虚拟消息列表属性 */
interface VirtualMessageListProps {
  /** 消息列表 */
  messages: Message[];
  /** 是否正在加载 */
  loading: boolean;
  /** 消息是否已出现 */
  messageAppeared: boolean;
  /** 用户是否手动滚动 */
  userScrolledRef: React.MutableRefObject<boolean>;
  /** 容器引用（用于宽度计算） */
  containerRef: React.RefObject<HTMLDivElement | null>;
  /** 聊天 ID（用于缓存清理） */
  chatId?: string;
  /** 高亮的消息 ID（搜索结果跳转定位） */
  highlightMessageId?: string | null;
  /** 外部跳转：赋值后可调用 ref.current(index) 跳转到指定消息 */
  scrollToMessageRef?: React.MutableRefObject<((index: number) => void) | null>;
  /** 外部 scrollToBottom：赋值后可调用 ref.current() 平滑滚动到底部 */
  scrollToBottomRef?: React.MutableRefObject<(() => void) | null>;
  /** 用户滚动状态变化回调（true=已滚离底部, false=回到底部） */
  onUserScrolledChange?: (scrolledUp: boolean) => void;
}

/** 默认消息高度估算 */
const DEFAULT_MESSAGE_HEIGHT = 200;

/** 可视区域外额外渲染的消息数 */
const OVERSCAN = 5;

/**
 * 虚拟消息列表
 *
 * 核心优化：
 * 1. 只渲染可视区域内的消息
 * 2. 动态测量消息高度并缓存
 * 3. 流式更新时自动滚动到底部
 */
const VirtualMessageList = memo<VirtualMessageListProps>(
  ({
    messages,
    loading,
    messageAppeared,
    userScrolledRef,
    containerRef: _containerRef,
    chatId,
    highlightMessageId,
    scrollToMessageRef,
    scrollToBottomRef,
    onUserScrolledChange,
  }) => {
    const parentRef = useRef<HTMLDivElement>(null);
    const { heightCache, setHeight, clearCache } = useMessageHeights();
    const prevChatIdRef = useRef(chatId);
    const highlightScrolledRef = useRef(false);

    // 聊天切换时清理高度缓存
    useEffect(() => {
      if (chatId && chatId !== prevChatIdRef.current) {
        clearCache();
        highlightScrolledRef.current = false;
        prevChatIdRef.current = chatId;
      }
    }, [chatId, clearCache]);

    // 虚拟化器
    const virtualizer = useVirtualizer({
      count: messages.length,
      getScrollElement: () => parentRef.current,
      estimateSize: (index) => {
        const messageId = messages[index]?.messageId;
        if (messageId && heightCache.has(messageId)) {
          return heightCache.get(messageId)!;
        }
        // 根据角色估算高度
        const role = messages[index]?.role;
        return role === 'user' ? 80 : DEFAULT_MESSAGE_HEIGHT;
      },
      overscan: OVERSCAN,
      // 启用动态测量
      measureElement: (element) => {
        return element.getBoundingClientRect().height;
      },
    });

    // 暴露 scrollToIndex 给外部（JumpBar 等组件使用）
    useEffect(() => {
      if (!scrollToMessageRef) return;
      scrollToMessageRef.current = (index: number) => {
        userScrolledRef.current = true;
        virtualizer.scrollToIndex(index, { align: 'start', behavior: 'smooth' });
      };
      return () => {
        scrollToMessageRef.current = null;
      };
    }, [scrollToMessageRef, virtualizer, userScrolledRef]);

    const virtualItems = virtualizer.getVirtualItems();

    // 滚动到底部
    // 注意：流式更新时使用 auto 避免跳跃，用户操作时使用 smooth
    const scrollToBottom = useCallback(
      (smooth = false) => {
        if (!parentRef.current || userScrolledRef.current) return;
        virtualizer.scrollToIndex(messages.length - 1, {
          align: 'end',
          behavior: smooth ? 'smooth' : 'auto',
        });
      },
      [messages.length, virtualizer, userScrolledRef],
    );

    // 暴露 scrollToBottom 给外部（ScrollToBottomButton 使用）
    useEffect(() => {
      if (!scrollToBottomRef) return;
      scrollToBottomRef.current = () => {
        userScrolledRef.current = false;
        onUserScrolledChange?.(false);
        virtualizer.scrollToIndex(messages.length - 1, { align: 'end', behavior: 'smooth' });
      };
      return () => {
        scrollToBottomRef.current = null;
      };
    }, [scrollToBottomRef, virtualizer, messages.length, userScrolledRef, onUserScrolledChange]);

    // 流式更新时自动滚动
    useEffect(() => {
      const lastMessage = messages[messages.length - 1];
      if (lastMessage?.role === 'assistant' && loading) {
        // 流式更新使用 auto 滚动，避免跳跃
        scrollToBottom(false);
      }
      // 用户发送消息时滚动（使用 smooth）
      if (lastMessage?.role === 'user') {
        userScrolledRef.current = false;
        scrollToBottom(true);
      }
    }, [messages, loading, scrollToBottom, userScrolledRef]);

    // 搜索结果跳转：滚动到高亮消息
    useEffect(() => {
      if (!highlightMessageId || highlightScrolledRef.current || messages.length === 0) return;
      const targetIndex = messages.findIndex((m) => String(m.messageId) === highlightMessageId);
      if (targetIndex >= 0) {
        highlightScrolledRef.current = true;
        userScrolledRef.current = true;
        requestAnimationFrame(() => {
          virtualizer.scrollToIndex(targetIndex, { align: 'center', behavior: 'smooth' });
        });
      }
    }, [highlightMessageId, messages, virtualizer, userScrolledRef]);

    const { loadOlderMessages, hasMoreMessages, loadingOlder } = useChatStore();
    const loadingOlderRef = useRef(false);

    // 监听滚动事件，检测用户是否手动滚动 + 向上加载更多
    useEffect(() => {
      const scrollElement = parentRef.current;
      if (!scrollElement) return;

      let lastScrollTop = scrollElement.scrollTop;

      const handleScroll = () => {
        const currentScrollTop = scrollElement.scrollTop;
        const scrollHeight = scrollElement.scrollHeight;
        const clientHeight = scrollElement.clientHeight;
        const isNearBottom = scrollHeight - currentScrollTop - clientHeight < 100;
        const isNearTop = currentScrollTop < 200;

        if (currentScrollTop < lastScrollTop - 5) {
          if (!userScrolledRef.current) {
            userScrolledRef.current = true;
            onUserScrolledChange?.(true);
          }
        }
        if (currentScrollTop > lastScrollTop + 5 && isNearBottom) {
          if (userScrolledRef.current) {
            userScrolledRef.current = false;
            onUserScrolledChange?.(false);
          }
        }

        if (isNearTop && hasMoreMessages && !loadingOlderRef.current) {
          loadingOlderRef.current = true;
          const prevHeight = scrollHeight;
          loadOlderMessages().finally(() => {
            loadingOlderRef.current = false;
            requestAnimationFrame(() => {
              if (parentRef.current) {
                const newHeight = parentRef.current.scrollHeight;
                parentRef.current.scrollTop = newHeight - prevHeight + currentScrollTop;
              }
            });
          });
        }

        lastScrollTop = currentScrollTop;
      };

      scrollElement.addEventListener('scroll', handleScroll, { passive: true });
      return () => scrollElement.removeEventListener('scroll', handleScroll);
    }, [userScrolledRef, hasMoreMessages, loadOlderMessages, onUserScrolledChange]);

    // 处理消息高度测量
    const handleHeightMeasure = useCallback(
      (messageId: string, height: number) => {
        setHeight(messageId, height);
        // 通知虚拟化器重新计算
        virtualizer.measure();
      },
      [setHeight, virtualizer],
    );

    return (
      <div
        ref={parentRef}
        className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent"
        style={{
          // 使用容器高度，减去输入框区域
          height: 'calc(100vh - 200px)',
        }}
      >
        {/* 向上加载更多提示 */}
        {loadingOlder && (
          <div className="flex justify-center py-4">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
          </div>
        )}

        {/* 虚拟列表容器 */}
        <div
          className="mx-auto max-w-5xl px-4 md:px-0 relative"
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {/* 渲染可视区域内的消息 */}
          {virtualItems.map((virtualRow) => {
            const message = messages[virtualRow.index];
            const isLast = virtualRow.index === messages.length - 1;

            return (
              <div
                key={virtualRow.key}
                data-index={virtualRow.index}
                ref={virtualizer.measureElement}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <MessageRow
                  message={message}
                  messageIndex={virtualRow.index}
                  loading={loading}
                  isLast={isLast}
                  onHeightMeasure={handleHeightMeasure}
                  highlighted={!!highlightMessageId && String(message.messageId) === highlightMessageId}
                />
                {/* 分割线 */}
                {!isLast && message.role === 'assistant' && <div className="h-px w-full bg-secondary" />}
              </div>
            );
          })}
        </div>

        {/* 加载中占位 */}
        {loading && !messageAppeared && (
          <div className="mx-auto max-w-5xl px-4 md:px-0">
            <MessageBoxLoading />
          </div>
        )}

        {/* 底部填充空间 */}
        <div className="h-40 lg:h-[15rem] w-full" />
      </div>
    );
  },
);

VirtualMessageList.displayName = 'VirtualMessageList';

/**
 * 消息行组件
 *
 * 负责渲染单条消息，并测量其高度
 */
interface MessageRowProps {
  message: Message;
  messageIndex: number;
  loading: boolean;
  isLast: boolean;
  onHeightMeasure: (messageId: string, height: number) => void;
  highlighted?: boolean;
}

const MessageRow = memo<MessageRowProps>(({ message, messageIndex, loading, isLast, onHeightMeasure, highlighted }) => {
  const rowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = rowRef.current;
    if (!element) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const height = entry.contentRect.height;
        if (height > 0) {
          onHeightMeasure(message.messageId, height);
        }
      }
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, [message.messageId, onHeightMeasure]);

  return (
    <div
      ref={rowRef}
      className={highlighted ? 'ring-2 ring-primary/40 rounded-lg transition-all duration-1000' : undefined}
    >
      {message.isCompactedSummaryView ? (
        <CompactedSummaryView />
      ) : (
        <MessageBox message={message} messageIndex={messageIndex} loading={loading} isLast={isLast} />
      )}
    </div>
  );
});

MessageRow.displayName = 'MessageRow';

export default VirtualMessageList;
