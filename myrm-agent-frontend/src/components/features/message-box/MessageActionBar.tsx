'use client';

/**
 * [INPUT]
 * @/store/chat/types::Message (POS: Chat state and SSE event type definitions)
 * ./MemoryCitationsButton (POS: Chat message memory citation action)
 *
 * [OUTPUT]
 * MessageActionBar: Completed/streaming assistant message actions.
 *
 * [POS]
 * Chat assistant message action surface. It keeps MessageBox focused on message layout and rendering.
 */

import { type RefObject, useMemo } from 'react';
import { AlertTriangle, Activity } from 'lucide-react';
import { useTranslations, useLocale } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import { formatMessageTimestamp } from '@/lib/utils/timeUtils';
import Copy from '../message-actions/Copy';
import ExportMenu from '../message-actions/ExportMenu';
import MemoryFeedback from '../message-actions/MemoryFeedback';
import ReadAloud from '../message-actions/ReadAloud';
import RevertFiles from '../message-actions/RevertFiles';
import RegenerateMenu from '../message-actions/RegenerateMenu';
import SaveEvalCase from '../message-actions/SaveEvalCase';
import SiblingNav from '../message-actions/SiblingNav';
import SourcesButton from '../message-actions/SourcesButton';
import Undo from '../message-actions/Undo';
import SaveToWikiButton from '../message-actions/SaveToWikiButton';
import TokenUsageDisplay from './TokenUsageDisplay';
import ConsensusMetaDisplay from './ConsensusMetaDisplay';
import MemoryCitationsButton from './MemoryCitationsButton';
import { ForkButton } from '../chat-window/ForkButton';
import type { Message } from '@/store/chat/types';

interface MessageActionBarProps {
  message: Message;
  messageIndex: number;
  loading: boolean;
  isLast: boolean;
  chatId?: string;
  enableEvalLab: boolean;
  markdownRef: RefObject<HTMLDivElement | null>;
  onCancel: () => Promise<void>;
  onRegenerate: (instruction?: string) => Promise<void>;
  onUndo: () => Promise<void>;
}

export default function MessageActionBar({
  message,
  messageIndex,
  loading,
  isLast,
  chatId,
  enableEvalLab,
  markdownRef,
  onCancel,
  onRegenerate,
  onUndo,
}: MessageActionBarProps) {
  const t = useTranslations('chat');
  const locale = useLocale();
  const isStreaming = isLast && loading;
  const setActiveSessionAnalyticsId = useChatStore((state) => state.setActiveSessionAnalyticsId);
  const setActiveSessionAnalyticsMessageId = useChatStore((state) => state.setActiveSessionAnalyticsMessageId);
  const timestamp = useMemo(
    () => (message.createdAt ? formatMessageTimestamp(message.createdAt, locale, t('dateGroup.yesterday')) : null),
    [message.createdAt, locale, t],
  );

  return (
    <div className="flex flex-row items-center justify-between w-full text-black dark:text-white py-4 -mx-2">
      <div className="flex flex-row items-center space-x-1">
        {isStreaming && (
          <button
            onClick={onCancel}
            className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-full transition-colors"
            title={t('cancel_request')}
            aria-label={t('cancel_request')}
          >
            <AlertTriangle className="w-4 h-4" />
          </button>
        )}
        {!isStreaming && <RegenerateMenu onRegenerate={onRegenerate} />}
        {!isStreaming && <Undo onUndo={onUndo} />}
        {!isStreaming && chatId && message.siblingGroupId && (message.siblingCount ?? 0) > 1 && (
          <SiblingNav
            chatId={chatId}
            siblingGroupId={message.siblingGroupId}
            siblingIndex={message.siblingIndex ?? 0}
            siblingCount={message.siblingCount ?? 0}
          />
        )}
        {!isStreaming && timestamp && (
          <span className="text-xs text-muted-foreground/60 ml-1 select-none" title={timestamp.title}>
            {timestamp.label}
          </span>
        )}
      </div>

      <div className="flex flex-row items-center space-x-1">
        {!isStreaming && message.sources && message.sources.length > 0 && <SourcesButton sources={message.sources} />}
        {!isStreaming && message.citedMemoryIds && message.citedMemoryIds.length > 0 && (
          <MemoryCitationsButton memoryIds={message.citedMemoryIds} references={message.citedMemoryRefs} />
        )}
        {!isStreaming && chatId && <RevertFiles chatId={chatId} messageId={message.messageId} />}
        {!isStreaming && message.citedMemoryIds && message.citedMemoryIds.length > 0 && (
          <MemoryFeedback memoryIds={message.citedMemoryIds} />
        )}
        {!isStreaming && <ReadAloud content={message.content} />}
        {!isStreaming && chatId && (
          <ForkButton chatId={chatId} messageIndex={messageIndex} />
        )}
        {!isStreaming && <SaveToWikiButton message={message} />}
        {!isStreaming && <Copy message={message} markdownRef={markdownRef} />}
        {!isStreaming && <ExportMenu message={message} markdownRef={markdownRef} />}
        {!isStreaming && enableEvalLab && chatId && <SaveEvalCase chatId={chatId} />}
        {!isStreaming && chatId && (
          <button
            type="button"
            onClick={() => {
              setActiveSessionAnalyticsMessageId(message.messageId);
              setActiveSessionAnalyticsId(chatId);
            }}
            className="p-2 text-black/70 dark:text-white/70 hover:bg-light-secondary dark:hover:bg-dark-secondary rounded-xl transition duration-200 hover:text-black dark:hover:text-white active:scale-95"
            title={t('performanceDiagnostics')}
            aria-label={t('performanceDiagnostics')}
          >
            <Activity className="w-4 h-4" />
          </button>
        )}
        {message.usage && (
          <TokenUsageDisplay
            chatId={chatId}
            messageId={message.messageId}
            usage={message.usage}
            tokenEconomics={message.tokenEconomics}
            costUsd={message.costUsd}
            costStatus={message.costStatus}
            cacheBreakReason={message.cacheBreakReason}
            cacheSuggestedActions={message.cacheSuggestedActions}
            modelName={message.modelName}
            routingTier={message.routingTier}
            modelTier={message.modelTier}
            privacyLevel={message.privacyLevel}
            privacyAction={message.privacyAction}
            privacyRoute={message.privacyRoute}
            contextBudget={message.contextBudget}
          />
        )}
        {message.consensusMeta && <ConsensusMetaDisplay meta={message.consensusMeta} />}
      </div>
    </div>
  );
}
