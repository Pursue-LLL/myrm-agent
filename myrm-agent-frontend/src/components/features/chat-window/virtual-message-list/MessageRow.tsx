/**
 * 虚拟列表的单条消息行
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - @/store/chat/types::Message (POS: 消息类型定义)
 * - ../../message-box/MessageBox (POS: 消息气泡)
 * - ../CompactedSummaryView (POS: 压缩摘要行)
 *
 * [OUTPUT]
 * - MessageRow: 单条消息行
 *   - 压缩摘要行渲染 CompactedSummaryView，其余渲染 MessageBox
 *   - 高亮的消息带一圈高亮环
 *   - 非末条的助手消息下方带分隔线
 *   - 每次提交后上报实测高度（高度大于 0 才上报）
 *
 * [POS]
 * 虚拟列表的行内容。行的渲染和高度测量封在 memo 组件里，
 * 滚动时只有内容或高亮变化的行才会重渲染。
 */

'use client';

import { useRef, useEffect, memo } from 'react';
import type { Message } from '@/store/chat/types';
import MessageBox from '../../message-box/MessageBox';
import { CompactedSummaryView } from '../CompactedSummaryView';

/** 单条消息行属性 */
interface MessageRowProps {
  message: Message;
  messageIndex: number;
  loading: boolean;
  isLast: boolean;
  highlightMessageId?: string | null;
  onHeightMeasure: (messageId: string, height: number) => void;
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
      if (rowRef.current && message?.messageId) {
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

export { MessageRow };
