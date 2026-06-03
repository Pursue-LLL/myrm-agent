'use client';

/**
 * [INPUT]
 * - message-box/MarkdownContent (POS: Markdown renderer for assistant messages)
 * - store/chat/types::Message (POS: Chat message entity)
 *
 * [OUTPUT]
 * - ReplayMessageBubble: read-only user/assistant message bubble for replay panes
 *
 * [POS]
 * Replay message rendering helper. Keeps Markdown parity with live chat UI.
 */

import { memo } from 'react';
import MarkdownContent from '@/components/features/message-box/MarkdownContent';
import type { Message } from '@/store/chat/types';

interface ReplayMessageBubbleProps {
  message: Message;
}

const ReplayMessageBubble = memo<ReplayMessageBubbleProps>(({ message }) => {
  if (message.role === 'user') {
    return (
      <div className="text-sm max-w-[95%] text-blue-600 dark:text-blue-400 self-end bg-blue-500/10 px-3 py-2 rounded-lg whitespace-pre-wrap break-words">
        {message.content}
      </div>
    );
  }

  return (
    <div className="text-sm max-w-[95%] text-foreground self-start break-words">
      <MarkdownContent
        content={message.content}
        sources={message.sources ?? []}
        messageId={message.messageId}
        isStreaming={false}
      />
    </div>
  );
});

ReplayMessageBubble.displayName = 'ReplayMessageBubble';
export default ReplayMessageBubble;
