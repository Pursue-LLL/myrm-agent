'use client';

/**
 * [INPUT]
 * @/store/useChatStore::Message (POS: Chat state store and message state façade)
 * ./assistant-message/AssistantMessage (POS: Bubble of one assistant answer)
 * ./UserMessage (POS: Bubble of one user message)
 * ./userMessageResend (POS: Resend flows of a user bubble, retry of a failed send and edit-and-resend)
 * ./useShowSystemMessages (POS: Reader of the developer-mode switch that reveals system-role rows)
 * ./WakeupNoticeRow (POS: Quiet transcript line for a settled background task that did not wake the agent)
 * ./CustomMessageCard (POS: Card of a custom (plugin) message)
 * ./MarkdownContent (POS: Markdown answer renderer)
 *
 * [OUTPUT]
 * MessageBox: Renders one chat message across user, assistant and system roles.
 *
 * [POS]
 * Role router of one chat message row: it picks the system, custom, wakeup-notice, user or assistant rendering and owns
 * the edit state of user rows. The assistant answer itself is rendered by `assistant-message/AssistantMessage`.
 */

import React, { useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useChatStore, { Message } from '@/store/useChatStore';
import { AssistantMessage } from './assistant-message/AssistantMessage';
import { CustomMessageCard } from './CustomMessageCard';
import MarkdownContent from './MarkdownContent';
import UserMessage from './UserMessage';
import { resendEditedUserMessage, retryFailedUserMessage } from './userMessageResend';
import { useShowSystemMessages } from './useShowSystemMessages';
import { WakeupNoticeRow } from './WakeupNoticeRow';

const MessageBox = ({
  message,
  messageIndex,
  loading,
  isLast,
}: {
  message: Message;
  messageIndex: number;
  loading: boolean;
  isLast: boolean;
}) => {
  const showSystemMessages = useShowSystemMessages();
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const chatId = useChatStore((state) => (typeof state.chatId === 'string' ? state.chatId : undefined));
  const t = useTranslations('chat');

  // System message (only shown in developer mode)
  if (message.role === 'system') {
    if (!showSystemMessages) {
      return null; // Hide system messages by default
    }

    return (
      <div className="flex flex-col space-y-2 my-4">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
          <span className="text-xs font-medium text-yellow-700 dark:text-yellow-300">
            {t('systemPromptDeveloperMode')}
          </span>
        </div>
        <div className="p-4 bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-800 rounded-lg">
          <div className="prose dark:prose-invert max-w-none text-sm">
            <MarkdownContent content={message.content} sources={[]} messageId={message.messageId} />
          </div>
        </div>
      </div>
    );
  }

  if (
    message.role === 'custom_message' ||
    (message as { extraData?: { is_custom_message?: boolean } }).extraData?.is_custom_message
  ) {
    const extra =
      (
        message as {
          extraData?: {
            custom_type?: string;
            display?: boolean;
            retention?: 'ephemeral' | 'persistent';
            details?: Record<string, unknown>;
          };
        }
      ).extraData || {};
    if (extra.display === false) {
      return null;
    }
    return (
      <CustomMessageCard
        customType={extra.custom_type || 'plugin'}
        content={message.content}
        display={extra.display ?? true}
        retention={extra.retention || 'persistent'}
        details={extra.details}
        timestamp={message.createdAt}
      />
    );
  }

  if (message.role === 'user' && message.wakeupNotice) {
    // The note that woke the agent sits behind the reply it caused; the others leave the chat waiting for the user.
    return message.wakeupNotice === 'followup' ? null : <WakeupNoticeRow kind={message.wakeupNotice} />;
  }

  if (message.role === 'user') {
    const handleEdit = () => setEditingMessageId(message.messageId);

    const handleEditSubmit = (newContent: string) => {
      if (loading || !chatId) {
        return;
      }
      setEditingMessageId(null);
      void resendEditedUserMessage(chatId, message, newContent);
    };

    const handleCancelEdit = () => setEditingMessageId(null);

    const handleFailedRetry = message.sendFailed ? () => void retryFailedUserMessage(message) : undefined;

    return (
      <UserMessage
        content={message.content}
        messageId={message.messageId}
        chatId={chatId}
        messageIndex={messageIndex}
        isFirst={messageIndex === 0}
        createdAt={message.createdAt}
        isEditing={editingMessageId === message.messageId}
        isLoading={loading}
        continuityBlocked={loading}
        onEdit={handleEdit}
        onEditSubmit={handleEditSubmit}
        onCancelEdit={handleCancelEdit}
        onRetry={handleFailedRetry}
        sendFailed={message.sendFailed}
        files={message.files}
        spillover={message.spillover}
      />
    );
  }

  return (
    <AssistantMessage message={message} messageIndex={messageIndex} loading={loading} isLast={isLast} chatId={chatId} />
  );
};

export default React.memo(MessageBox);
