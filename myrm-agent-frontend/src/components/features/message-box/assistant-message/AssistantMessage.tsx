'use client';

/**
 * [INPUT]
 * @/store/useChatStore::Message (POS: Chat state store and message state façade)
 * @/lib/citations/buildCitationSources (POS: Citation source resolver of an answer; SSOT for which source a marker number names)
 * ../MarkdownContent (POS: Markdown answer renderer)
 * ../MessageActionBar (POS: Chat assistant message action surface)
 * ./AssistantRunOutputs (POS: Run outputs shown above the answer)
 * ./CompletionStatusNotice (POS: Banner of an answer that ended abnormally)
 * ./messagePayloads (POS: Typed readers of the loosely typed message payload)
 * ./useAssistantMessageActions (POS: Regenerate and cancel of the latest turn)
 * ./useReasoningAutoCollapse (POS: Open / folded state of the reasoning block)
 *
 * [OUTPUT]
 * AssistantMessage: Renders the bubble of one assistant answer.
 *
 * [POS]
 * The assistant bubble: the run outputs, then the answer block with its reasoning, markdown, quote toolbar, interactive
 * cards, cost and memory panels, action bar, notices and suggestions. It reads the chat stores itself, so rows of other
 * roles never subscribe to them.
 */

import { useMemo, useRef, type RefObject } from 'react';
import { Disc3 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { findLastTurnAnswerId } from '@/lib/chat/lastTurnAnswer';
import { buildCitationSources } from '@/lib/citations/buildCitationSources';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import useChatStore, { Message } from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import ClarificationInput from '../ClarificationInput';
import { DeliverableTierBadge } from '../DeliverableTierBadge';
import { FileMutationWarning } from '../FileMutationWarning';
import { HumanGateCard } from '../HumanGateCard';
import MarkdownContent from '../MarkdownContent';
import MemoryInsightPanel from '../MemoryInsightPanel';
import { resolveMessageCreatedAtMs } from '../memoryLifecyclePhases';
import MessageActionBar from '../MessageActionBar';
import { MessageToc } from '../MessageToc';
import { ModelSpecialtyChip } from '../ModelSpecialtyChip';
import PlanConfirmationCard from '../PlanConfirmationCard';
import { QuoteToolbar, useQuoteSelection } from '../QuoteToolbar';
import ReasoningProcessAccordion from '../ReasoningProcessAccordion';
import { StagedArtifactsNotice } from '../StagedArtifactsNotice';
import Suggestions from '../Suggestions';
import WaitingTtftIndicator from '../WaitingTtftIndicator';
import WaterDropCostView from '../WaterDropCostView';
import WorkflowSuggestionCard from '../WorkflowSuggestionCard';
import WorkflowTemplateSaveCard from '../WorkflowTemplateSaveCard';
import { AssistantRunOutputs } from './AssistantRunOutputs';
import { CompletionStatusNotice } from './CompletionStatusNotice';
import { closeUnbalancedReasoningTags, parseAsyncTaskResponse, parseTtsAudioResponse } from './messagePayloads';
import { useAssistantMessageActions } from './useAssistantMessageActions';
import { useReasoningAutoCollapse } from './useReasoningAutoCollapse';

export function AssistantMessage({
  message,
  messageIndex,
  loading,
  isLast,
  chatId,
}: {
  message: Message;
  messageIndex: number;
  loading: boolean;
  isLast: boolean;
  /** Id of the open chat; undefined while none is open. */
  chatId: string | undefined;
}) {
  const markdownRef = useRef<HTMLDivElement>(null);
  const { state: quoteState, dismiss: dismissQuote } = useQuoteSelection(markdownRef);
  const messages = useChatStore((state) => state.messages);
  const composerPendingClarification = useMemo(() => findActivePendingClarification(messages), [messages]);
  // Regenerate acts on the latest turn only, so only that turn's answer offers it.
  const isLastTurnAnswer = useMemo(
    () => message.role === 'assistant' && findLastTurnAnswerId(messages) === message.messageId,
    [messages, message.role, message.messageId],
  );
  const hideInlineClarification = composerPendingClarification?.messageId === message.messageId;
  // Approval cards render inline under the assistant message that produced them,
  // so the pending flag is derived from the global approval queue keyed by messageId.
  const approvalPending = useToolApprovalStore((state) =>
    state.queue.some((request) => request.messageId === message.messageId),
  );
  const workspaceDir = useChatStore((state) => state.workspaceDir ?? undefined);
  const enableEvalLab = useConfigStore((state) => state.enableEvalLab);
  const reasoningDisplayMode = useConfigStore(
    (state) => state.personalSettings?.reasoningDisplayMode ?? state.reasoningDisplayMode ?? 'collapsed',
  );
  const parsedMessage = useMemo(
    () => (message.role === 'assistant' ? closeUnbalancedReasoningTags(message.content) : message.content || ''),
    [message.content, message.role],
  );
  const t = useTranslations('chat');
  const hasKbEvidenceOnCurrentMessage = useMemo(
    () =>
      message.sources?.some((source) => Boolean(source.kb_name) && Boolean(source.snippet || source.summary)) ?? false,
    [message.sources],
  );

  const { isExpanded: isReasoningExpanded, toggle: toggleReasoning } = useReasoningAutoCollapse({
    isLast,
    loading,
    content: message.content,
    reasoning: message.reasoning,
    displayMode: reasoningDisplayMode,
  });
  const { handleRegenerate, handleCancel } = useAssistantMessageActions({
    message,
    chatId,
    hasKbEvidence: hasKbEvidenceOnCurrentMessage,
  });

  // 检测是否为异步任务响应（如图片生成）
  const taskResponse = useMemo(() => parseAsyncTaskResponse(message.content), [message.content]);

  // 检测是否为 tts_generate 同步成功响应（就地播放而非裸 JSON 渲染）
  const ttsAudioResponse = useMemo(() => parseTtsAudioResponse(message.content), [message.content]);

  // A marker in this answer names a source of this message first, then the nearest earlier message that has that number.
  const citationSources = useMemo(
    () => buildCitationSources(messages.slice(0, messageIndex), message.sources ?? []),
    [messages, messageIndex, message.sources],
  );

  return (
    <div data-test-id="assistant-message" className="flex flex-col space-y-9 relative">
      <div className="flex flex-col space-y-6 w-full">
        <AssistantRunOutputs
          message={message}
          loading={loading}
          isLast={isLast}
          chatId={chatId}
          approvalPending={approvalPending}
          taskResponse={taskResponse}
          ttsAudioResponse={ttsAudioResponse}
        />

        {/* 回复 */}
        {!taskResponse && !ttsAudioResponse && (
          <div className="flex flex-col space-y-2">
            <div className="flex flex-row items-center justify-between">
              <div className="flex flex-row items-center space-x-2">
                <Disc3
                  className={cn(
                    'text-black dark:text-white',
                    // 只在生成答案步骤且正在加载时旋转
                    isLast &&
                      loading &&
                      (() => {
                        const lastStepKey =
                          message.progressSteps?.[message.progressSteps.length - 1]?.step_key?.toLowerCase() || '';
                        return lastStepKey.includes('generating') || lastStepKey.includes('answer');
                      })()
                      ? 'animate-spin'
                      : 'animate-none',
                  )}
                  size={20}
                />
                <h3 className="text-gray-800 dark:text-gray-100 font-medium text-lg">{t('answer')}</h3>
              </div>
              <div className="flex items-center gap-2">
                {message.routingSpecialty && (
                  <ModelSpecialtyChip specialty={message.routingSpecialty} modelName={message.modelName} />
                )}
                {message.deliverableTier && !(isLast && loading) && (
                  <DeliverableTierBadge data={message.deliverableTier} />
                )}
              </div>
            </div>

            {/* Reasoning display */}
            {message.reasoning && reasoningDisplayMode !== 'off' && (
              <ReasoningProcessAccordion
                message={message}
                isLast={isLast}
                loading={loading}
                isExpanded={isReasoningExpanded}
                onToggle={toggleReasoning}
                displayMode={reasoningDisplayMode}
              />
            )}

            {/* TTFT indicator — visible only during pre-first-token blank period */}
            {isLast && loading && !parsedMessage && (!message.reasoning || reasoningDisplayMode === 'off') && (
              <WaitingTtftIndicator />
            )}

            {message.workflowSuggestion && (
              <WorkflowSuggestionCard messageId={message.messageId} status={message.workflowSuggestion.status} />
            )}

            <MessageToc
              content={parsedMessage}
              messageId={message.messageId}
              isStreaming={isLast && loading}
              containerRef={markdownRef as RefObject<HTMLElement>}
            />

            <div
              ref={markdownRef}
              data-message-id={message.messageId}
              className={cn('transition-opacity duration-200', message.isFadingOut ? 'opacity-0' : 'opacity-100')}
            >
              <MarkdownContent
                content={parsedMessage}
                sources={citationSources}
                messageId={message.messageId}
                isStreaming={isLast && loading}
                chatId={chatId}
                messageArtifacts={message.artifacts}
                workspaceDir={workspaceDir}
              />
              {/* 流式输出动画 - 渐进变深的三个圆点，每个延迟 0.2s 形成波浪效果 */}
              {isLast && loading && parsedMessage && !message.isFadingOut && (
                <span className="inline-flex items-center ml-1.5 gap-0.5 align-middle" aria-label="Loading">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-[pulse_1s_ease-in-out_infinite]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-[pulse_1s_ease-in-out_0.2s_infinite]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-warm/70 animate-[pulse_1s_ease-in-out_0.4s_infinite]" />
                </span>
              )}
            </div>

            <QuoteToolbar state={quoteState} onDismiss={dismissQuote} />

            {/* Clarification 输入（Composer takeover 时由 MessageInput 承载） */}
            {message.clarification && !hideInlineClarification && (
              <ClarificationInput
                messageId={message.messageId}
                answered={message.clarification.answered}
                options={message.clarification.options}
                allowMultiple={message.clarification.allowMultiple}
                answerRecord={message.clarification.answerRecord}
                title={message.clarification.title}
                form={message.clarification.form}
              />
            )}

            {message.planConfirmation && (
              <PlanConfirmationCard
                messageId={message.messageId}
                plan={message.planConfirmation.plan}
                status={message.planConfirmation.status}
                planItems={message.planConfirmation.planItems}
                goal={message.planConfirmation.goal}
                source={message.planConfirmation.source}
                spawnCount={message.planConfirmation.spawnCount}
                estimatedCostUsd={message.planConfirmation.estimatedCostUsd}
                remainingBudgetUsd={message.planConfirmation.remainingBudgetUsd}
                costStatus={message.planConfirmation.costStatus}
              />
            )}

            {message.humanGate && (
              <HumanGateCard
                messageId={message.messageId}
                question={message.humanGate.question}
                options={message.humanGate.options}
                timeoutSeconds={message.humanGate.timeoutSeconds}
                defaultAction={message.humanGate.defaultAction}
                status={message.humanGate.status}
                answer={message.humanGate.answer}
                timedOut={message.humanGate.timedOut}
              />
            )}

            <WaterDropCostView
              usage={message.usage}
              tokenEconomics={message.tokenEconomics}
              costUsd={message.costUsd}
              isStreaming={isLast && loading}
            />

            <MemoryInsightPanel
              chatId={chatId}
              isLast={isLast}
              isStreaming={isLast && loading}
              messageCreatedAtMs={resolveMessageCreatedAtMs(message.createdAt)}
              memoryBrief={message.memoryBrief}
              memoryBriefStatus={message.memoryBriefStatus}
              memoryBudget={message.memoryBudget}
              citations={message.citations}
            />

            <MessageActionBar
              message={message}
              messageIndex={messageIndex}
              loading={loading}
              isLast={isLast}
              isLastTurnAnswer={isLastTurnAnswer}
              chatId={chatId}
              enableEvalLab={enableEvalLab}
              markdownRef={markdownRef}
              onCancel={handleCancel}
              onRegenerate={handleRegenerate}
            />

            {/* 文件修改失败警告 */}
            {!(isLast && loading) && message.fileMutationFailures && message.fileMutationFailures.length > 0 && (
              <FileMutationWarning failures={message.fileMutationFailures} />
            )}

            {/* 自动暂存的未落盘交付物草案通知条 */}
            {!(isLast && loading) && message.stagedArtifacts && message.stagedArtifacts.length > 0 && (
              <StagedArtifactsNotice stagedArtifacts={message.stagedArtifacts} />
            )}

            {!(isLast && loading) && chatId && message.role === 'assistant' && (
              <WorkflowTemplateSaveCard message={message} chatId={chatId} />
            )}

            <CompletionStatusNotice status={message.completionStatus} streaming={isLast && loading} />

            {/* 建议 */}
            {isLast && <Suggestions message={message} loading={loading} />}
          </div>
        )}
      </div>
    </div>
  );
}
