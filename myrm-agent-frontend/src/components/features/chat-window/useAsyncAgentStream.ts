/**
 * [INPUT]
 * - window event `async-agent-stream-chunk` (POS: 后台 Agent 推送到当前页面的流分片)
 * - @/store/chat/messageStreamHandler::handleMessageStream (POS: 把流事件归并进消息状态，按需动态加载)
 * - @/store/useChatStore (POS: 用户自己回合的 loading 状态与消息写入口)
 *
 * [OUTPUT]
 * - useAsyncAgentStream: 把属于当前会话的后台 Agent 分片按到达顺序交给流处理器
 *
 * [POS]
 * ChatWindow 的后台流层。用户自己的回合正在流式（loading）时分片先进收件箱暂存，回合结束再补放，
 * 避免两条流同时写同一份消息；空闲时分片直接处理。
 */

import { useEffect, useRef } from 'react';
import { AdaptiveScheduler } from '@/store/chat/adaptiveScheduler';
import type { StreamHandlerActions, StreamHandlerState, StreamMutableState } from '@/store/chat/messageStreamHandler';
import type { AgentStreamEvent, ChatState } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

interface AsyncAgentStreamChunkDetail {
  session_id: string;
  chunk: AgentStreamEvent;
}

export function useAsyncAgentStream(id: string | undefined): void {
  const asyncSchedulerRef = useRef<AdaptiveScheduler | null>(null);
  const pendingInboxRef = useRef<AgentStreamEvent[]>([]);

  useEffect(() => {
    const processInbox = async () => {
      if (pendingInboxRef.current.length === 0) {
        return;
      }
      // 双流防撞锁：用户自己的回合在流式时分片留在收件箱，回合结束后由下面的订阅补放
      if (useChatStore.getState().loading) {
        return;
      }

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
        chatId: id,
        actionMode: useChatStore.getState().actionMode,
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
      const { session_id, chunk } = (e as CustomEvent<AsyncAgentStreamChunkDetail>).detail;

      // 只处理当前会话的流数据
      if (session_id !== id) {
        return;
      }

      // 所有分片先进收件箱，保证到达顺序；用户自己的回合在流式（loading）时 processInbox 不会取走分片
      pendingInboxRef.current.push(chunk);
      void processInbox();
    };

    // 监听全局的 loading 状态变化，当对话结束（loading 变为 false）时，恢复执行 inbox 中的积压任务
    const unsubscribe = useChatStore.subscribe((state, prevState) => {
      if (prevState.loading === true && state.loading === false) {
        void processInbox();
      }
    });

    window.addEventListener('async-agent-stream-chunk', handleAsyncChunk);

    return () => {
      window.removeEventListener('async-agent-stream-chunk', handleAsyncChunk);
      unsubscribe();
    };
  }, [id]);
}
