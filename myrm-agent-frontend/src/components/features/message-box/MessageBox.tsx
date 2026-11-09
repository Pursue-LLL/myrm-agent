'use client';

/**
 * [INPUT]
 * @/store/useChatStore::Message (POS: Chat state store and message state façade)
 * ./MarkdownContent (POS: Markdown answer renderer)
 * ./MessageActionBar (POS: Chat assistant message action surface)
 * ./userMessageResend (POS: Resend flows of a user bubble, retry of a failed send and edit-and-resend)
 * ./useShowSystemMessages (POS: Reader of the developer-mode switch that reveals system-role rows)
 * ./WakeupNoticeRow (POS: Quiet transcript line for a settled background task that did not wake the agent)
 * components/features/task-card/{ImageTaskCard,VideoTaskCard} (POS: Async media task cards)
 * @/lib/citations/buildCitationSources (POS: Citation source resolver of an answer; SSOT for which source a marker number names)
 *
 * [OUTPUT]
 * MessageBox: Renders one chat message across user, assistant and system roles.
 *
 * [POS]
 * Chat message layout coordinator. It owns per-message rendering branches and delegates specialized actions,
 * markdown, artifacts and approvals to focused child components.
 */

import React, { useState, useRef, useMemo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { AlertTriangle, Ban, Disc3, ShieldAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import useChatStore, { Message } from '@/store/useChatStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useConfigStore from '@/store/useConfigStore';
import { buildCitationSources } from '@/lib/citations/buildCitationSources';
import { findLastTurnAnswerId } from '@/lib/chat/lastTurnAnswer';
import ProgressSteps from './progress-steps/ProgressSteps';
import { messageHasSkillManageUndo } from './progress-steps/skillManageBatch';
import { SkillManageUndoHintCard } from './SkillManageUndoHintCard';
import { EvidenceStageHUD } from '@/components/features/chat-window/EvidenceStageHUD';
import { ExecutionPhaseStepper } from '@/components/features/chat-window/ExecutionPhaseStepper';
import ConsensusThinkingPanel from './ConsensusThinkingPanel';
import UserMessage from './UserMessage';
import { WakeupNoticeRow } from './WakeupNoticeRow';
import { resendEditedUserMessage, retryFailedUserMessage } from './userMessageResend';
import { useShowSystemMessages } from './useShowSystemMessages';
import MarkdownContent from './MarkdownContent';
import WaitingTtftIndicator from './WaitingTtftIndicator';
import Suggestions from './Suggestions';
import ArtifactsDisplay from '@/components/features/artifacts/ArtifactsDisplay';
import ArtifactErrorBoundary from '@/components/features/artifacts/ArtifactErrorBoundary';
import { CustomMessageCard } from './CustomMessageCard';
import ClarificationInput from './ClarificationInput';
import PlanConfirmationCard from './PlanConfirmationCard';
import { HumanGateCard } from './HumanGateCard';
import WorkflowSuggestionCard from './WorkflowSuggestionCard';
import MessageActionBar from './MessageActionBar';
import { ImageTaskCard, VideoTaskCard } from '@/components/features/task-card';
import TtsAudioCard from './TtsAudioCard';
import { CronJobSystemCard } from './CronJobSystemCard';
import { KanbanTaskCreatedCard } from './KanbanTaskCreatedCard';
import { QuoteToolbar, useQuoteSelection } from './QuoteToolbar';
import WaterDropCostView from './WaterDropCostView';
import MemoryInsightPanel from './MemoryInsightPanel';
import { resolveMessageCreatedAtMs } from './memoryLifecyclePhases';
import { FileMutationWarning } from './FileMutationWarning';
import { StagedArtifactsNotice } from './StagedArtifactsNotice';
import WorkflowTemplateSaveCard from './WorkflowTemplateSaveCard';
import ToolImageGallery from './ToolImageGallery';
import SessionRecordingCard from './SessionRecordingCard';
import VisualApprovalInlineSection from '@/components/features/chat-window/approval/VisualApprovalInlineSection';
import { CouncilResultCard } from '@/components/features/chat-window/CouncilResultCard';
import { MessageToc } from './MessageToc';
import { McpAppSection } from './McpAppSection';
import { DeliverableTierBadge } from './DeliverableTierBadge';
import { ModelSpecialtyChip } from './ModelSpecialtyChip';
import ReasoningProcessAccordion from './ReasoningProcessAccordion';
import {
  closeUnbalancedReasoningTags,
  parseAsyncTaskResponse,
  parseTtsAudioResponse,
  readCronJobResult,
  readKanbanTasksCreated,
  readMcpApps,
  readSessionRecording,
  readToolImages,
  resolveProgressSteps,
} from './assistant-message/messagePayloads';
import { useAssistantMessageActions } from './assistant-message/useAssistantMessageActions';
import { useReasoningAutoCollapse } from './assistant-message/useReasoningAutoCollapse';

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
  const chatId = useChatStore((state) => (typeof state.chatId === 'string' ? state.chatId : undefined));
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
  const tProgress = useTranslations('progressSteps');
  const hasKbEvidenceOnCurrentMessage = useMemo(
    () =>
      message.sources?.some((source) => Boolean(source.kb_name) && Boolean(source.snippet || source.summary)) ?? false,
    [message.sources],
  );

  const sessionRecordingData = readSessionRecording(message);
  const toolImages = readToolImages(message);
  const mcpApps = readMcpApps(message);
  const cronJobResult = readCronJobResult(message);
  const kanbanTasksCreated = readKanbanTasksCreated(message);
  const sessionRecordingCard: React.ReactNode = sessionRecordingData ? (
    <SessionRecordingCard filename={sessionRecordingData.filename} previewUrl={sessionRecordingData.preview_url} />
  ) : null;

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

  if (!message) {
    return null;
  }

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
    <div data-test-id="assistant-message" className="flex flex-col space-y-9 relative">
      <div className="flex flex-col space-y-6 w-full">
        {message.mediaAnalysisStatus && (
          <div className="inline-flex flex-col gap-1">
            <div className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-2.5 text-sm font-medium text-primary backdrop-blur-sm">
              <span
                className="inline-block h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin"
                aria-hidden="true"
              />
              <span>{tProgress(message.mediaAnalysisStatus)}</span>
            </div>
            {message.visionBackend && (
              <span className="text-xs text-muted-foreground px-1">
                {tProgress(`visionBackend.${message.visionBackend}` as 'visionBackend.vlm')}
              </span>
            )}
          </div>
        )}

        {/* 进度步骤与执行阶段 HUD */}
        {(() => {
          const resolvedProgressSteps = resolveProgressSteps(message);
          return (
            <div className="space-y-1.5">
              {(message.phaseExecution || (loading && isLast)) && (
                <ExecutionPhaseStepper
                  phaseExecution={message.phaseExecution}
                  phaseHistory={message.phaseHistory}
                  loading={loading && isLast}
                  isApprovalPending={approvalPending}
                />
              )}
              {resolvedProgressSteps.length > 0 && (
                <>
                  <EvidenceStageHUD steps={resolvedProgressSteps} loading={loading} />
                  <ProgressSteps messageId={message.messageId} steps={resolvedProgressSteps} loading={loading} />
                  {messageHasSkillManageUndo(resolvedProgressSteps) && !(loading && isLast) ? (
                    <SkillManageUndoHintCard messageId={message.messageId} />
                  ) : null}
                </>
              )}
            </div>
          );
        })()}

        {message.consensusRefs && message.consensusRefs.length > 0 && (
          <ConsensusThinkingPanel
            refs={message.consensusRefs}
            isStreaming={isLast && loading && !message.content}
            totalExpected={message.consensusRefsExpected}
          />
        )}

        {/* 可视化审批 Artifact（BBox 高亮截图卡片） */}
        <VisualApprovalInlineSection messageId={message.messageId} chatId={chatId ?? null} />

        {/* 多专家 Council 编排会商与仲裁结果卡片 */}
        {message.councilResult && <CouncilResultCard councilResult={message.councilResult} />}

        {/* 工件 */}
        {message.artifacts && message.artifacts.length > 0 && (
          <ArtifactsDisplay artifacts={message.artifacts} chatId={chatId} />
        )}

        {/* 工具截屏图片（如 computer_use） */}
        {toolImages.length > 0 && <ToolImageGallery images={toolImages} />}

        {/* 会话录制回放 */}
        {sessionRecordingCard}

        {/* MCP Apps (ext-apps) 嵌入式 UI */}
        {mcpApps.length > 0 && (
          <ArtifactErrorBoundary fallbackMessage={t('mcpAppRenderFailed')}>
            <McpAppSection views={mcpApps} />
          </ArtifactErrorBoundary>
        )}

        {/* 异步任务卡片（如图片生成） */}
        {taskResponse &&
          (taskResponse.task_type === 'video_generate' ? (
            <VideoTaskCard task_id={taskResponse.task_id} />
          ) : (
            <ImageTaskCard task_id={taskResponse.task_id} />
          ))}

        {/* TTS 语音合成结果：就地播放卡片 */}
        {ttsAudioResponse && (
          <TtsAudioCard
            url={ttsAudioResponse.audio_url}
            model={ttsAudioResponse.model}
            durationSeconds={ttsAudioResponse.duration_seconds}
          />
        )}

        {/* 定时任务创建/更新卡片 */}
        {cronJobResult ? <CronJobSystemCard result={cronJobResult} /> : null}

        {/* Kanban 任务创建卡片 */}
        {kanbanTasksCreated.length > 0 && chatId
          ? kanbanTasksCreated.map((item) => <KanbanTaskCreatedCard key={item.task_id} result={item} chatId={chatId} />)
          : null}

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
              containerRef={markdownRef as React.RefObject<HTMLElement>}
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

            {/* 完成状态提示 */}
            {!(isLast && loading) && message.completionStatus === 'truncated' && (
              <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-sm">
                <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                <span className="text-amber-700 dark:text-amber-300">{t('message.truncated')}</span>
              </div>
            )}
            {!(isLast && loading) && message.completionStatus === 'cancelled' && (
              <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-muted/40 border border-border/50 rounded-lg text-sm text-muted-foreground">
                <Ban className="w-4 h-4 text-muted-foreground/70 shrink-0" />
                <span>{t('message.cancelled')}</span>
              </div>
            )}
            {!(isLast && loading) && message.completionStatus === 'filtered' && (
              <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg text-sm">
                <ShieldAlert className="w-4 h-4 text-red-500 shrink-0" />
                <span className="text-red-700 dark:text-red-300">{t('message.contentFiltered')}</span>
              </div>
            )}
            {!(isLast && loading) && message.completionStatus === 'budget_blocked' && (
              <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800 rounded-lg text-sm">
                <Ban className="w-4 h-4 text-orange-500 shrink-0" />
                <span className="text-orange-700 dark:text-orange-300">{t('message.budgetBlocked')}</span>
              </div>
            )}

            {/* 建议 */}
            {isLast && <Suggestions message={message} loading={loading} />}
          </div>
        )}
      </div>
    </div>
  );
};

export default React.memo(MessageBox);
