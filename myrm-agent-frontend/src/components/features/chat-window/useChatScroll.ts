/**
 * [INPUT]
 * - @/hooks/ui/useScrollPositionRestore (POS: 阅读位置的内存 / sessionStorage 镜像)
 * - @/lib/utils/domUtils::isNearBottom (POS: window 是否接近页面底部)
 * - @/store/useChatStore (POS: 实时消息列表，供按 id 跳转读取)
 *
 * [OUTPUT]
 * - useChatScroll: 聊天列表的滚动控制
 *   - 阅读状态：是否滚离底部、是否有新内容、输入框是否露出
 *   - 跳转：按消息序号 / id 跳转，滚到底部
 *   - 自动跟随：流式输出与内容增高时跟到底部，用户上滑后不再打扰
 *   - 位置镜像：切换会话时读取、挂载后恢复、滚动停止后防抖保存
 *   - 高亮：每条高亮消息只居中一次（centeredHighlightRef 与虚拟列表共用），高亮参数消失后可再次居中
 *
 * [POS]
 * Chat 的滚动层。普通列表由 window 滚动，虚拟列表自己滚动并通过 scrollToMessageRef / virtualScrollToBottomRef
 * 把跳转与回到底部交给列表；两种模式共用同一套阅读状态。
 */

import { useCallback, useEffect, useRef, useState, type MutableRefObject, type RefObject } from 'react';
import { useScrollPositionRestore } from '@/hooks/ui/useScrollPositionRestore';
import { isNearBottom } from '@/lib/utils/domUtils';
import type { Message } from '@/store/chat/types/messages';
import useChatStore from '@/store/useChatStore';

interface ChatScrollOptions {
  chatId: string | undefined;
  messages: Message[];
  loading: boolean;
  highlightMessageId: string | null;
}

export interface ChatScroll {
  /** 普通列表的消息列容器，也是按 id 查找消息节点的范围。 */
  containerRef: RefObject<HTMLDivElement | null>;
  /** 普通列表末尾的哨兵节点。 */
  messageEnd: RefObject<HTMLDivElement | null>;
  showInput: boolean;
  isUserScrolledUp: boolean;
  hasNewMessage: boolean;
  userScrolledRef: MutableRefObject<boolean>;
  /** 虚拟列表挂载后写入：按序号滚动。 */
  scrollToMessageRef: MutableRefObject<((index: number) => void) | null>;
  /** 虚拟列表挂载后写入：滚到底部。 */
  virtualScrollToBottomRef: MutableRefObject<(() => void) | null>;
  /** 已居中过的高亮消息 id：同一条高亮只居中一次，两种列表共用；高亮参数消失后清空。 */
  centeredHighlightRef: MutableRefObject<string | null>;
  handleJumpToMessage: (messageIndex: number) => void;
  handleJumpToMessageId: (messageId: string) => void;
  handleVirtualScrollStateChange: (scrolledUp: boolean) => void;
  handleScrollToBottomClick: () => void;
}

export function useChatScroll({ chatId, messages, loading, highlightMessageId }: ChatScrollOptions): ChatScroll {
  const messageEnd = useRef<HTMLDivElement | null>(null);
  const lastScrollPositionRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const [showInput, setShowInput] = useState(true);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const virtualScrollToBottomRef = useRef<(() => void) | null>(null);
  const scrollToMessageRef = useRef<((index: number) => void) | null>(null);
  const centeredHighlightRef = useRef<string | null>(null);

  // 使用滚动位置保存/恢复 Hook（支持双模态流式跟随与视口镜像）
  const {
    saveScrollPosition,
    restoreScrollPosition,
    getScrollMirrorSnapshot,
    userScrolledRef,
    isFollowingBottomRef,
    saveTimerRef,
  } = useScrollPositionRestore({
    id: chatId,
    enabled: true,
    onRestore: (entry) => {
      setIsUserScrolledUp(entry.isUserScrolledUp);
      if (!entry.isUserScrolledUp) {
        setHasNewMessage(false);
      }
    },
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
      if (!msg) {
        return;
      }
      const el = containerRef.current?.querySelector(`[data-message-id="${CSS.escape(String(msg.messageId))}"]`);
      if (el) {
        userScrolledRef.current = true;
        setIsUserScrolledUp(true);
        saveScrollPosition({
          isFollowingBottom: false,
          isUserScrolledUp: true,
          anchorMessageId: String(msg.messageId),
        });
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    },
    [messages, userScrolledRef, saveScrollPosition],
  );

  const handleJumpToMessageId = useCallback(
    (messageId: string) => {
      userScrolledRef.current = true;
      setIsUserScrolledUp(true);

      const performJump = () => {
        // 解耦闭包，优先从最新的状态仓库获取消息列表
        const currentMessages = useChatStore.getState().messages;
        const targetIndex = currentMessages.findIndex((m) => String(m.messageId) === messageId);

        if (targetIndex >= 0 && scrollToMessageRef.current) {
          scrollToMessageRef.current(targetIndex);
          return true;
        }

        const el = containerRef.current?.querySelector(`[data-message-id="${CSS.escape(messageId)}"]`);
        if (el) {
          saveScrollPosition({
            isFollowingBottom: false,
            isUserScrolledUp: true,
            anchorMessageId: messageId,
          });
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          return true;
        }
        return false;
      };

      // 立即尝试第 1 次
      if (performJump()) {
        return;
      }

      // 双帧 RAF 调度（Double RequestAnimationFrame）：防御跨分页加载时的 React DOM commit 异步挂载延迟
      requestAnimationFrame(() => {
        if (!performJump()) {
          requestAnimationFrame(() => {
            performJump();
          });
        }
      });
    },
    [userScrolledRef, saveScrollPosition],
  );

  // VirtualMessageList 滚动状态变化回调
  const handleVirtualScrollStateChange = useCallback((scrolledUp: boolean) => {
    setIsUserScrolledUp(scrolledUp);
    if (!scrolledUp) {
      setHasNewMessage(false);
    }
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
    isFollowingBottomRef.current = true;
    setIsUserScrolledUp(false);
    setHasNewMessage(false);
    saveScrollPosition({ isFollowingBottom: true, isUserScrolledUp: false });
    if (messageEnd.current) {
      messageEnd.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    setShowInput(true);
  }, [userScrolledRef, isFollowingBottomRef, saveScrollPosition]);

  // 立即滚动函数，完全无延迟
  const scrollToBottom = useCallback(() => {
    if (!messageEnd.current || userScrolledRef.current) {
      return;
    }

    messageEnd.current.scrollIntoView({
      behavior: 'smooth',
      block: 'end',
    });
    setShowInput(true);
  }, [userScrolledRef]);

  // 聊天切换时从持久化镜像同步状态，避免直接暴击清零
  useEffect(() => {
    const snapshot = getScrollMirrorSnapshot();
    if (snapshot) {
      // oxlint-disable-next-line react/set-state-in-effect -- copies the persisted scroll mirror (memory map + sessionStorage), which lives outside React
      setIsUserScrolledUp(snapshot.isUserScrolledUp);
      userScrolledRef.current = snapshot.isUserScrolledUp;
      isFollowingBottomRef.current = snapshot.isFollowingBottom;
    } else {
      setIsUserScrolledUp(false);
      userScrolledRef.current = false;
      isFollowingBottomRef.current = true;
    }
    setHasNewMessage(false);
  }, [chatId, getScrollMirrorSnapshot, userScrolledRef, isFollowingBottomRef]);

  // 组件挂载时恢复滚动位置
  useEffect(() => {
    if (messages.length > 0) {
      const timer = setTimeout(restoreScrollPosition, 100);
      return () => clearTimeout(timer);
    }
  }, [messages.length, restoreScrollPosition, chatId]);

  // 高亮消息只居中一次：高亮参数留在地址栏里，流式更新不能再把视口拽回去；参数消失后同一条可以再次居中
  useEffect(() => {
    if (!highlightMessageId) {
      centeredHighlightRef.current = null;
      return;
    }
    if (centeredHighlightRef.current === highlightMessageId) {
      return;
    }
    const el = containerRef.current?.querySelector(`[data-message-id="${CSS.escape(highlightMessageId)}"]`);
    if (el) {
      centeredHighlightRef.current = highlightMessageId;
      requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    }
  }, [highlightMessageId, messages]);

  // 处理滚动事件（合并输入框显示/隐藏逻辑和滚动位置保存逻辑）
  useEffect(() => {
    // 初始化上次滚动位置
    lastScrollPositionRef.current = window.scrollY;

    const handleScroll = () => {
      const currentScrollPosition = window.scrollY;
      const scrollDelta = currentScrollPosition - lastScrollPositionRef.current;

      // 向上滚动且超过 5px 阈值：视为用户主动离开底部
      if (scrollDelta < -5) {
        if (!userScrolledRef.current) {
          userScrolledRef.current = true;
          setIsUserScrolledUp(true);
        }
        setShowInput(false);
      }

      // 向下滚动超过 5px 并且到了底部附近，才重置标志
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

  // ResizeObserver 回调读取最新的 loading，避免因 loading 变化重建观察者
  const loadingRef = useRef(loading);
  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  // 监听容器大小变化，用于处理内容突然增加的情况
  // 仅在 loading 状态下才自动滚动，避免用户手动展开/折叠时触发
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const observer = new ResizeObserver((entries) => {
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

    observer.observe(container);

    return () => {
      observer.disconnect();
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
    if (lastMessage?.role === 'user') {
      userScrolledRef.current = false;
      // oxlint-disable-next-line react/set-state-in-effect -- the user's own message landing in the chat store ends the away-from-bottom state
      setIsUserScrolledUp(false);
      setHasNewMessage(false);
      scrollToBottom();
    }
  }, [messages, loading, scrollToBottom, userScrolledRef]);

  return {
    containerRef,
    messageEnd,
    showInput,
    isUserScrolledUp,
    hasNewMessage,
    userScrolledRef,
    scrollToMessageRef,
    virtualScrollToBottomRef,
    centeredHighlightRef,
    handleJumpToMessage,
    handleJumpToMessageId,
    handleVirtualScrollStateChange,
    handleScrollToBottomClick,
  };
}
