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
 * - @/hooks/ui/useScrollPositionRestore (POS: 滚动跟随持久化镜像总线)
 *
 * [OUTPUT]
 * - VirtualMessageList: 虚拟滚动消息列表组件
 *   - 只渲染可视区域内的消息
 *   - 支持动态高度
 *   - 支持流式更新自动滚动
 *   - 支持向上滚动加载历史
 *   - 支持搜索结果跳转定位和高亮
 *   - 支持 L1/L2 自动滚动跟随与视口持久化镜像恢复
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
import { useScrollPositionRestore } from '@/hooks/ui/useScrollPositionRestore';
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
  /** 容器 Ref（用于获取宽度等） */
  containerRef?: React.RefObject<HTMLDivElement | null>;
  /** 聊天 ID（切换时清理高度缓存） */
  chatId?: string;
  /** 搜索结果高亮的消息 ID */
  highlightMessageId?: string | null;
  /** 外部跳转到指定消息：赋值后可调用 ref.current(index) */
  scrollToMessageRef?: React.MutableRefObject<((index: number) => void) | null>;
  /** 外部 scrollToBottom：赋值后可调用 ref.current() 平滑滚动到底部 */
  scrollToBottomRef?: React.MutableRefObject<(() => void) | null>;
  /** 用户滚动状态变化回调（通知外部显示/隐藏滚动到底部按钮） */
  onUserScrolledChange?: (userScrolled: boolean) => void;
}

/** 默认消息估算高度 */
const DEFAULT_MESSAGE_HEIGHT = 150;
/** 缓冲区大小（上下各渲染多少个额外项） */
const OVERSCAN = 3;

/**
 * 虚拟消息列表
 *
 * 核心优化：
 * 1. 只渲染可视区域内的消息
 * 2. 动态测量消息高度并缓存
 * 3. 流式更新时自动滚动到底部
 * 4. 接入 useScrollPositionRestore，实现会话切换 0ms 滚动镜像恢复
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

    // 虚拟滚动容器获取器
    const getScrollElement = useCallback(() => parentRef.current, []);

    // 接入通用滚动跟随与视口持久化镜像总线
    const { saveScrollPosition, restoreScrollPosition, saveTimerRef } = useScrollPositionRestore({
      id: chatId,
      enabled: Boolean(chatId),
      getScrollElement,
      onRestore: (entry) => {
        if (entry.isUserScrolledUp) {
          userScrolledRef.current = true;
          onUserScrolledChange?.(true);
        } else {
          userScrolledRef.current = false;
          onUserScrolledChange?.(false);
        }
      },
    });

    // 聊天切换时清理高度缓存与高亮标记
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

    // 恢复滚动镜像（当消息加载后尝试恢复）
    useEffect(() => {
      if (messages.length > 0 && parentRef.current) {
        const timer = setTimeout(() => {
          restoreScrollPosition();
        }, 50);
        return () => clearTimeout(timer);
      }
    }, [messages.length, chatId, restoreScrollPosition]);

    // 暴露 scrollToIndex 给外部（JumpBar 等组件使用）
    useEffect(() => {
      if (!scrollToMessageRef) {
        return;
      }
      scrollToMessageRef.current = (index: number) => {
        userScrolledRef.current = true;
        onUserScrolledChange?.(true);
        virtualizer.scrollToIndex(index, { align: 'start', behavior: 'smooth' });
        saveScrollPosition({ isFollowingBottom: false, isUserScrolledUp: true });
      };
      return () => {
        scrollToMessageRef.current = null;
      };
    }, [scrollToMessageRef, virtualizer, userScrolledRef, onUserScrolledChange, saveScrollPosition]);

    const virtualItems = virtualizer.getVirtualItems();

    // 滚动到底部
    // 注意：流式更新时使用 auto 避免跳跃，用户操作时使用 smooth
    const scrollToBottom = useCallback(
      (smooth = false) => {
        if (!parentRef.current || userScrolledRef.current) {
          return;
        }
        virtualizer.scrollToIndex(messages.length - 1, {
          align: 'end',
          behavior: smooth ? 'smooth' : 'auto',
        });
      },
      [messages.length, virtualizer, userScrolledRef],
    );

    // 暴露 scrollToBottom 给外部（ScrollToBottomButton 使用）
    useEffect(() => {
      if (!scrollToBottomRef) {
        return;
      }
      scrollToBottomRef.current = () => {
        userScrolledRef.current = false;
        onUserScrolledChange?.(false);
        virtualizer.scrollToIndex(messages.length - 1, { align: 'end', behavior: 'smooth' });
        saveScrollPosition({ isFollowingBottom: true, isUserScrolledUp: false });
      };
      return () => {
        scrollToBottomRef.current = null;
      };
    }, [scrollToBottomRef, virtualizer, messages.length, userScrolledRef, onUserScrolledChange, saveScrollPosition]);

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
        onUserScrolledChange?.(false);
        scrollToBottom(true);
      }
    }, [messages, loading, scrollToBottom, userScrolledRef, onUserScrolledChange]);

    // 搜索结果跳转：滚动到高亮消息
    useEffect(() => {
      if (!highlightMessageId || highlightScrolledRef.current || messages.length === 0) {
        return;
      }
      const targetIndex = messages.findIndex((m) => String(m.messageId) === highlightMessageId);
      if (targetIndex >= 0) {
        highlightScrolledRef.current = true;
        userScrolledRef.current = true;
        onUserScrolledChange?.(true);
        requestAnimationFrame(() => {
          virtualizer.scrollToIndex(targetIndex, { align: 'center', behavior: 'smooth' });
          saveScrollPosition({ isFollowingBottom: false, isUserScrolledUp: true });
        });
      }
    }, [highlightMessageId, messages, virtualizer, userScrolledRef, onUserScrolledChange, saveScrollPosition]);

    const { loadOlderMessages, hasMoreMessages, loadingOlder } = useChatStore();
    const loadingOlderRef = useRef(false);

    // 监听滚动事件，检测用户是否手动滚动 + 向上加载更多 + 防抖持久化镜像
    useEffect(() => {
      const scrollElement = parentRef.current;
      if (!scrollElement) {
        return;
      }

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

        // 防抖保存当前滚动状态镜像
        if (saveTimerRef.current) {
          clearTimeout(saveTimerRef.current);
        }
        saveTimerRef.current = setTimeout(() => {
          saveScrollPosition();
        }, 200);

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
      return () => {
        scrollElement.removeEventListener('scroll', handleScroll);
        if (saveTimerRef.current) {
          clearTimeout(saveTimerRef.current);
        }
      };
    }, [userScrolledRef, hasMoreMessages, loadOlderMessages, onUserScrolledChange, saveScrollPosition, saveTimerRef]);

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
                  highlightMessageId={highlightMessageId}
                  onHeightMeasure={handleHeightMeasure}
                />
              </div>
            );
          })}
        </div>

        {/* 底部加载中指示器 */}
        {loading && !messageAppeared && (
          <div className="py-4">
            <MessageBoxLoading />
          </div>
        )}

        {/* 底部安全间距，避免内容被浮动输入框遮挡 */}
        <div className="h-44 w-full shrink-0" />
      </div>
    );
  },
);

VirtualMessageList.displayName = 'VirtualMessageList';

/** 单条消息行组件属性 */
interface MessageRowProps {
  message: Message;
  messageIndex: number;
  loading: boolean;
  isLast: boolean;
  highlightMessageId?: string | null;
  onHeightMeasure?: (messageId: string, height: number) => void;
}

/**
 * 单条消息行组件
 * 封装单条消息的渲染逻辑，便于高度测量
 */
const MessageRow = memo<MessageRowProps>(
  ({ message, messageIndex, loading, isLast, highlightMessageId, onHeightMeasure }) => {
    const rowRef = useRef<HTMLDivElement>(null);

    // 测量高度并通知父组件
    useEffect(() => {
      if (rowRef.current && message?.messageId && onHeightMeasure) {
        const height = rowRef.current.getBoundingClientRect().height;
        if (height > 0) {
          onHeightMeasure(message.messageId, height);
        }
      }
    });

    if (message?.isCompactedSummaryView) {
      return (
        <div ref={rowRef} data-message-id={message.messageId} data-testid="compacted-summary-view">
          <CompactedSummaryView />
        </div>
      );
    }

    const isHighlighted = !!highlightMessageId && String(message.messageId) === highlightMessageId;

    return (
      <div
        ref={rowRef}
        data-message-id={message.messageId}
        className={isHighlighted ? 'ring-2 ring-primary/40 rounded-lg transition-all duration-1000' : undefined}
      >
        <MessageBox message={message} messageIndex={messageIndex} loading={loading} isLast={isLast} />
        {!isLast && message.role === 'assistant' && <div className="h-px w-full bg-secondary" />}
      </div>
    );
  },
);

MessageRow.displayName = 'MessageRow';

export default VirtualMessageList;
export { VirtualMessageList };
