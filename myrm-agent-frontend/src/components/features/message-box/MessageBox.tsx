'use client';

/**
 * [INPUT]
 * @/store/useChatStore::Message (POS: Chat state store and message state façade)
 * ./MarkdownContent (POS: Markdown answer renderer)
 * ./MessageActionBar (POS: Chat assistant message action surface)
 * components/features/task-card/{ImageTaskCard,VideoTaskCard} (POS: Async media task cards)
 *
 * [OUTPUT]
 * MessageBox: Renders one chat message across user, assistant and system roles.
 *
 * [POS]
 * Chat message layout coordinator. It owns per-message rendering branches and delegates specialized actions,
 * markdown, artifacts, approvals and async task cards to focused child components.
 */

/* eslint-disable @next/next/no-img-element */
import React, { useEffect, useState, useRef, useMemo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { AlertTriangle, Ban, Disc3, ShieldAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import useChatStore, { Message } from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import type { McpAppView, Source, ToolCallInfo, ToolImageOutput, UIArtifact } from '@/store/chat/types';
import { resolveSourceClickUrl } from '@/store/chat/types/sources';
import { stripDatetimeTag } from '@/lib/utils/messageUtils';
import { regenerateLastTurn, undoLastTurn, cancelAgentRequest, truncateAfterMessage } from '@/services/chat';
import ProgressSteps from './progress-steps/ProgressSteps';
import ConsensusThinkingPanel from './ConsensusThinkingPanel';
import UserMessage from './UserMessage';
import MarkdownContent from './MarkdownContent';
import Suggestions from './Suggestions';
import ArtifactsDisplay from '@/components/features/artifacts/ArtifactsDisplay';
import { InteractiveUIDisplay } from '@/components/features/interactive-ui';
import ArtifactErrorBoundary from '@/components/features/artifacts/ArtifactErrorBoundary';
import { UIActionEvent } from '@/store/chat/types';
import { formatUIActionAsMessage, type UIActionMessageLabels } from '@/components/features/interactive-ui/utils';
import ToolCallApproval from './ToolCallApproval';
import ClarificationInput from './ClarificationInput';
import PlanConfirmationCard from './PlanConfirmationCard';
import WorkflowSuggestionCard from './WorkflowSuggestionCard';
import MessageActionBar from './MessageActionBar';
import { useCLIAgentStore } from '@/store/useCLIAgentStore';
import { CLIDiffViewer } from '@/components/features/cli-visualization/CLIDiffViewer';
import { isTauriEnvironment } from '@/lib/tauri';
import { ImageTaskCard, VideoTaskCard } from '@/components/features/task-card';
import { CronJobSystemCard } from './CronJobSystemCard';
import { KanbanTaskCreatedCard, type KanbanTaskCreatedResult } from './KanbanTaskCreatedCard';
import { QuoteToolbar, useQuoteSelection } from './QuoteToolbar';
import WaterDropCostView from './WaterDropCostView';
import MemoryInsightPanel from './MemoryInsightPanel';
import { FileMutationWarning } from './FileMutationWarning';
import ToolImageGallery from './ToolImageGallery';
import SessionRecordingCard from './SessionRecordingCard';
import VisualApprovalInlineSection from '@/components/features/chat-window/VisualApprovalInlineSection';
import { ChevronDown, ChevronRight, BrainCircuit } from 'lucide-react';
import { MessageToc } from './MessageToc';
import { McpAppSection } from './McpAppSection';

const ReasoningBlock = ({
  message,
  isLast,
  loading,
  isExpanded,
  onToggle,
}: {
  message: Message;
  isLast: boolean;
  loading: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}) => {
  const t = useTranslations('chat');
  const isThinking = isLast && loading && !message.content;
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (!isThinking || !message.reasoningStartedAt) {
      setElapsedSec(0);
      return;
    }
    setElapsedSec(Math.floor((Date.now() - message.reasoningStartedAt) / 1000));
    const timer = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - message.reasoningStartedAt!) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [isThinking, message.reasoningStartedAt]);

  const durationSec = message.reasoningDurationMs ? Math.round(message.reasoningDurationMs / 1000) : null;

  const label = isThinking
    ? t('reasoningThinking', { seconds: elapsedSec })
    : durationSec
      ? t('reasoningCompleted', { seconds: durationSec })
      : t('reasoningTitle');

  return (
    <div className="mb-4 border border-border/50 rounded-lg overflow-hidden bg-muted/20">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 transition-colors text-sm"
      >
        <div className="flex items-center gap-2 text-muted-foreground">
          <BrainCircuit className="w-4 h-4" />
          <span className="font-medium">{label}</span>
        </div>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
        )}
      </button>
      {isExpanded && (
        <div className="px-4 py-3 border-t border-border/50 text-sm text-muted-foreground bg-muted/10">
          <MarkdownContent
            content={message.reasoning!}
            sources={[]}
            messageId={`${message.messageId}-reasoning`}
            isStreaming={isThinking}
          />
          {isThinking && (
            <span className="inline-flex items-center ml-1.5 gap-0.5 align-middle" aria-label="Loading">
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-[pulse_1s_ease-in-out_infinite]" />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-[pulse_1s_ease-in-out_0.2s_infinite]" />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-[pulse_1s_ease-in-out_0.4s_infinite]" />
            </span>
          )}
        </div>
      )}
    </div>
  );
};

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
  const [parsedMessage, setParsedMessage] = useState('');
  const [showSystemMessages, setShowSystemMessages] = useState(false);
  const [isReasoningExpanded, setIsReasoningExpanded] = useState(
    () => isLast && loading && !message.content,
  );
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const markdownRef = useRef<HTMLDivElement>(null);
  const { state: quoteState, dismiss: dismissQuote } = useQuoteSelection(markdownRef);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const messages = useChatStore((state) => state.messages);
  const composerPendingClarification = useMemo(
    () => findActivePendingClarification(messages),
    [messages],
  );
  const hideInlineClarification =
    composerPendingClarification?.messageId === message.messageId;
  const chatId = useChatStore((state) => (typeof state.chatId === 'string' ? state.chatId : undefined));
  const enableEvalLab = useConfigStore((state) => state.enableEvalLab);
  const previousContentRef = useRef('');
  const t = useTranslations('chat');
  const tProgress = useTranslations('progressSteps');
  const tUiAction = useTranslations('interactiveUI.userAction');

  const uiActionMessageLabels: UIActionMessageLabels = useMemo(
    () => ({
      header: tUiAction('header'),
      actionLabel: tUiAction('actionLabel'),
      dataLabel: tUiAction('dataLabel'),
      emptyField: tUiAction('emptyField'),
      actionTypes: {
        submit: tUiAction('actionTypes.submit'),
        cancel: tUiAction('actionTypes.cancel'),
        navigate: tUiAction('actionTypes.navigate'),
        custom: tUiAction('actionTypes.custom'),
      },
    }),
    [tUiAction],
  );

  const sessionRecordingData: { filename: string; preview_url: string } | null =
    message.sessionRecording &&
    typeof message.sessionRecording === 'object' &&
    typeof message.sessionRecording.filename === 'string' &&
    typeof message.sessionRecording.preview_url === 'string'
      ? message.sessionRecording
      : null;
  const toolImages: ToolImageOutput[] = Array.isArray(message.toolImages)
    ? (message.toolImages as ToolImageOutput[])
    : [];
  const uiArtifacts: UIArtifact[] = Array.isArray(message.uiArtifacts)
    ? (message.uiArtifacts as UIArtifact[])
    : [];
  const mcpApps: McpAppView[] = Array.isArray(message.mcpApps)
    ? (message.mcpApps as McpAppView[])
    : [];
  const toolCalls: ToolCallInfo[] = Array.isArray(message.toolCalls)
    ? (message.toolCalls as ToolCallInfo[])
    : [];
  const cronJobResult =
    message.metadata &&
    typeof message.metadata === 'object' &&
    'cron_job_result' in message.metadata
      ? (message.metadata.cron_job_result as import('./CronJobSystemCard').CronJobResult)
      : null;
  const kanbanTasksCreated = (() => {
    if (!message.metadata || typeof message.metadata !== 'object') return [];
    const raw = message.metadata.kanban_tasks_created;
    if (Array.isArray(raw)) {
      return raw.filter(
        (item): item is KanbanTaskCreatedResult =>
          typeof item === 'object' &&
          item !== null &&
          typeof (item as KanbanTaskCreatedResult).task_id === 'string' &&
          typeof (item as KanbanTaskCreatedResult).title === 'string' &&
          typeof (item as KanbanTaskCreatedResult).board_id === 'string',
      );
    }
    return [];
  })();
  const sessionRecordingCard: React.ReactNode = sessionRecordingData ? (
    <SessionRecordingCard
      filename={sessionRecordingData.filename}
      previewUrl={sessionRecordingData.preview_url}
    />
  ) : null;

  useEffect(() => {
    const stored = localStorage.getItem('developer_show_system_messages');
    setShowSystemMessages(stored === 'true');

    const handleDeveloperModeChange = (e: Event) => {
      const customEvent = e as CustomEvent<{ showSystemMessages: boolean }>;
      setShowSystemMessages(customEvent.detail.showSystemMessages);
    };

    window.addEventListener('developer-mode-changed', handleDeveloperModeChange);
    return () => window.removeEventListener('developer-mode-changed', handleDeveloperModeChange);
  }, []);

  // 自动折叠思考过程：当思考结束（开始输出正文）时自动折叠
  useEffect(() => {
    if (message.reasoning && message.content && message.content.length > 0 && isReasoningExpanded) {
      setIsReasoningExpanded(false);
    }
  }, [message.content, message.reasoning]);

  // 处理交互式 UI 动作回传
  const handleUIAction = (event: UIActionEvent) => {
    const actionMessage = formatUIActionAsMessage(event, uiActionMessageLabels);
    sendMessage(actionMessage);
  };

  const handleRegenerate = async (instruction?: string) => {
    if (!chatId) return;

    try {
      const result = await regenerateLastTurn(chatId, instruction);

      if (result.success && result.query) {
        useChatStore.setState((state) => ({
          messages: state.messages.filter((m) => m.role !== 'assistant' || m.messageId !== message.messageId),
          regenerateSiblingGroupId: result.sibling_group_id,
          regenerateInstruction: instruction,
        }));

        const cleanQuery = stripDatetimeTag(result.query);
        await sendMessage(cleanQuery);
      }
    } catch (error) {
      console.error('Regenerate failed:', error);
    } finally {
      useChatStore.setState({ regenerateSiblingGroupId: undefined, regenerateInstruction: undefined });
    }
  };

  // 取消：调用后端 API 取消正在运行的 Agent 请求
  const handleCancel = async () => {
    try {
      const abortController = useChatStore.getState().abortController;
      await cancelAgentRequest(message.messageId);
      abortController?.abort(); // 关闭 SSE 连接
    } catch (error) {
      console.error('Cancel failed:', error);
    }
  };

  // 撤销：先调用后端 API 持久化删除整轮对话，再同步前端 UI 状态
  const handleUndo = async () => {
    if (!chatId) return;

    try {
      const result = await undoLastTurn(chatId);

      if (result.success && result.deleted_count > 0) {
        // 找到最后一条 user message 的位置，删除它及之后的所有消息
        let userMessageIndex = -1;
        for (let i = messageIndex - 1; i >= 0; i--) {
          if (messages[i]?.role === 'user') {
            userMessageIndex = i;
            break;
          }
        }

        if (userMessageIndex >= 0) {
          useChatStore.setState((state) => ({
            messages: state.messages.slice(0, userMessageIndex),
          }));
        }
      }
    } catch (error) {
      console.error('Undo failed:', error);
    }
  };

  if (!message) return null;

  // 检测是否为异步任务响应（如图片生成）
  const taskResponse = useMemo(() => {
    try {
      const parsed = JSON.parse(message.content);
      if (parsed.task_id && typeof parsed.task_id === 'string') {
        return parsed as { task_id: string; task_type?: string; status?: string; message?: string };
      }
    } catch {
      // 不是有效 JSON 或不包含 task_id，继续正常渲染
    }
    return null;
  }, [message.content]);

  // 累积当前会话中所有消息的 sources（从开始到当前消息）
  // 这样可以正确渲染引用了之前消息中 sources 的 【数字】 标记
  const accumulatedSources = useMemo(() => {
    const allSources: Source[] = [];
    const seenKeys = new Set<string>();

    // 遍历从开始到当前消息的所有消息
    for (let i = 0; i <= messageIndex && i < messages.length; i++) {
      const msg = messages[i];
      if (msg.sources) {
        for (const source of msg.sources) {
          // 生成唯一标识符用于去重
          // 优先使用 URL，其次使用 skill 名称组合，最后使用 kb/filename 组合
          let key: string;
          const clickUrl = resolveSourceClickUrl(source);
          if (clickUrl) {
            key = clickUrl;
          } else if (source.skill_name && source.calls && source.calls.length > 0) {
            // 使用 skill_name 和 calls 中的工具名称组合
            const toolNames = source.calls.map((c) => c.tool_name).join(',');
            key = `skill:${source.skill_name}:${toolNames}`;
          } else if (source.skill_name) {
            // 只有 skill_name 没有 calls
            key = `skill:${source.skill_name}`;
          } else if (source.kb_name && source.filename) {
            key = `kb:${source.kb_name}:${source.filename}`;
          } else {
            // 兜底：使用 index（如果有）或跳过去重
            key = source.index ? `index:${source.index}` : JSON.stringify(source);
          }

          if (!seenKeys.has(key)) {
            seenKeys.add(key);
            allSources.push(source);
          }
        }
      }
    }

    return allSources;
  }, [messages, messageIndex]);

  // 用于跟踪上次处理时的 sources 长度，确保 sources 更新时也能重新处理
  const previousSourcesLengthRef = useRef(0);

  useEffect(() => {
    const currentSourcesLength = accumulatedSources.length;
    const sourcesChanged = currentSourcesLength !== previousSourcesLengthRef.current;

    // 如果内容没变且 sources 也没变，跳过处理
    if (!message.content || (previousContentRef.current === message.content && !sourcesChanged)) {
      return;
    }

    // 用requestAnimationFrame批量处理内容更新，提高性能
    window.requestAnimationFrame(() => {
      previousContentRef.current = message.content;
      previousSourcesLengthRef.current = currentSourcesLength;
      let processedMessage = message.content;

      if (message.role === 'assistant' && processedMessage.includes('<')) {
        for (const tag of [
          'think',
          'thinking',
          'thought',
          'antthinking',
          'reasoning',
          'REASONING_SCRATCHPAD',
        ] as const) {
          const openRe = new RegExp(`<${tag}>`, 'gi');
          const closeRe = new RegExp(`</${tag}>`, 'gi');
          const openCount = processedMessage.match(openRe)?.length || 0;
          const closeCount = processedMessage.match(closeRe)?.length || 0;
          if (openCount > closeCount) {
            processedMessage += `</${tag}> <a> </a>`;
          }
        }
      }

      let finalContent = processedMessage;

      const citationRegex = /【(\d+)】/g;

      // 使用累积的 sources 来处理引用
      // 这样可以正确渲染引用了之前消息中 sources 的 【数字】 标记
      if (message.role === 'assistant' && accumulatedSources.length > 0) {
        finalContent = processedMessage.replace(citationRegex, (_, numStr: string) => {
          const number = parseInt(numStr);

          if (isNaN(number) || number <= 0) {
            return `[${numStr}]`;
          }

          // 从累积的 sources 中查找对应的来源
          const source = accumulatedSources[number - 1];

          // 只要有source就生成citation标签，不管是否有URL
          if (source) {
            const url = source?.url || '';
            return `<citation data-url="${url}" data-num="${numStr}" data-source-index="${number - 1}"></citation>`;
          } else {
            return `[${numStr}]`;
          }
        });
      }

      setParsedMessage(finalContent);
    });
  }, [message.content, message.role, accumulatedSources]);

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
            SYSTEM PROMPT (Developer Mode)
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

  if (message.role === 'user') {
    const handleEdit = () => setEditingMessageId(message.messageId);

    const handleEditSubmit = async (newContent: string) => {
      if (loading || !chatId) return;
      setEditingMessageId(null);

      try {
        await truncateAfterMessage(chatId, message.messageId);
      } catch (error) {
        console.error('Truncate failed:', error);
      }

      useChatStore.setState((state) => ({
        messages: state.messages.slice(0, messageIndex),
      }));
      sendMessage(newContent);
    };

    const handleCancelEdit = () => setEditingMessageId(null);

    const handleFailedRetry = message.sendFailed
      ? () => {
          const retryContent = stripDatetimeTag(message.content);
          useChatStore.setState((state) => ({
            messages: state.messages.filter((m) => m.messageId !== message.messageId),
          }));
          sendMessage(retryContent);
        }
      : undefined;

    return (
      <UserMessage
        content={message.content}
        messageId={message.messageId}
        isFirst={messageIndex === 0}
        createdAt={message.createdAt}
        isEditing={editingMessageId === message.messageId}
        isLoading={loading}
        onEdit={handleEdit}
        onEditSubmit={handleEditSubmit}
        onCancelEdit={handleCancelEdit}
        onRetry={handleFailedRetry}
        sendFailed={message.sendFailed}
        files={message.files}
      />
    );
  }

  return (
    <div data-test-id="assistant-message" className="flex flex-col space-y-9 relative">
      <div className="flex flex-col space-y-6 w-full">
        {message.mediaAnalysisStatus && (
          <div className="inline-flex items-center gap-2 rounded-2xl border border-primary/20 bg-primary/10 px-4 py-2.5 text-sm font-medium text-primary backdrop-blur-sm">
            <span
              className="inline-block h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin"
              aria-hidden="true"
            />
            <span>{tProgress(message.mediaAnalysisStatus)}</span>
          </div>
        )}

        {/* 进度步骤 */}
        {(() => {
          const resolvedProgressSteps =
            message.progressSteps && message.progressSteps.length > 0
              ? message.progressSteps
              : Array.isArray(message.metadata?.progressSteps)
                ? (message.metadata.progressSteps as typeof message.progressSteps)
                : [];
          if (!resolvedProgressSteps || resolvedProgressSteps.length === 0) {
            return null;
          }
          return (
            <ProgressSteps
              messageId={message.messageId}
              steps={resolvedProgressSteps}
              loading={loading}
            />
          );
        })()}

        {message.consensusRefs && message.consensusRefs.length > 0 && (
          <ConsensusThinkingPanel
            refs={message.consensusRefs}
            isStreaming={isLast && loading && !message.content}
          />
        )}

        {/* 可视化审批 Artifact（BBox 高亮截图卡片） */}
        <VisualApprovalInlineSection messageId={message.messageId} chatId={chatId ?? null} />

        {/* 工件 */}
        {message.artifacts && message.artifacts.length > 0 && (
          <ArtifactsDisplay artifacts={message.artifacts} chatId={chatId} />
        )}

        {/* 交互式 UI 工件 (A2UI) */}
        {uiArtifacts.length > 0 && (
          <ArtifactErrorBoundary fallbackMessage="Interactive UI failed to render">
            <InteractiveUIDisplay uiArtifacts={uiArtifacts} onAction={handleUIAction} />
          </ArtifactErrorBoundary>
        )}

        {/* 工具截屏图片（如 computer_use） */}
        {toolImages.length > 0 && <ToolImageGallery images={toolImages} />}

        {/* 会话录制回放 */}
        {sessionRecordingCard}

        {/* MCP Apps (ext-apps) 嵌入式 UI */}
        {mcpApps.length > 0 && (
          <ArtifactErrorBoundary fallbackMessage="MCP App failed to render">
            <McpAppSection views={mcpApps} />
          </ArtifactErrorBoundary>
        )}

        {/* CLI Agent 工具调用审批 */}
        {toolCalls.length > 0 && chatId && (
          <ToolCallApproval
            toolCalls={toolCalls}
            chatId={chatId}
            onApprove={async (callId) => {
              const { respondPermission } = useCLIAgentStore.getState();
              await respondPermission(callId, true);
            }}
            onReject={async (callId) => {
              const { respondPermission } = useCLIAgentStore.getState();
              await respondPermission(callId, false);
            }}
          />
        )}

        {/* CLI Agent Diff 预览（仅 Tauri 桌面环境） */}
        {isTauriEnvironment() &&
          toolCalls
            ?.filter((tc) => tc.diff)
            .map((tc) => <CLIDiffViewer key={tc.callId} diff={tc.diff!} filePath={tc.filePath} />)}

        {/* 异步任务卡片（如图片生成） */}
        {taskResponse &&
          (taskResponse.task_type === 'video_generate' ? (
            <VideoTaskCard task_id={taskResponse.task_id} />
          ) : (
            <ImageTaskCard task_id={taskResponse.task_id} />
          ))}

        {/* 定时任务创建/更新卡片 */}
        {cronJobResult ? <CronJobSystemCard result={cronJobResult} /> : null}

        {/* Kanban 任务创建卡片 */}
        {kanbanTasksCreated.length > 0 && chatId
          ? kanbanTasksCreated.map((item) => (
              <KanbanTaskCreatedCard key={item.task_id} result={item} chatId={chatId} />
            ))
          : null}

        {/* 回复 */}
        {!taskResponse && (
          <div className="flex flex-col space-y-2">
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

            {/* Reasoning display */}
            {message.reasoning && (
              <ReasoningBlock
                message={message}
                isLast={isLast}
                loading={loading}
                isExpanded={isReasoningExpanded}
                onToggle={() => setIsReasoningExpanded(!isReasoningExpanded)}
              />
            )}

            {/* TTFT indicator — visible only during pre-first-token blank period */}
            {isLast && loading && !parsedMessage && !message.reasoning && (
              <span className="inline-flex items-center gap-0.5 py-2" aria-label={t('thinking')}>
                <span className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-[pulse_1s_ease-in-out_infinite]" />
                <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-[pulse_1s_ease-in-out_0.2s_infinite]" />
                <span className="w-1.5 h-1.5 rounded-full bg-accent-warm/70 animate-[pulse_1s_ease-in-out_0.4s_infinite]" />
              </span>
            )}

            {message.workflowSuggestion && (
              <WorkflowSuggestionCard
                messageId={message.messageId}
                status={message.workflowSuggestion.status}
              />
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
                sources={accumulatedSources}
                messageId={message.messageId}
                isStreaming={isLast && loading}
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
                isResumeMode={message.clarification.isResumeMode}
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
              />
            )}

            <WaterDropCostView
              usage={message.usage}
              tokenEconomics={message.tokenEconomics}
              costUsd={message.costUsd}
              isStreaming={isLast && loading}
            />

            <MemoryInsightPanel 
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
              chatId={chatId}
              enableEvalLab={enableEvalLab}
              markdownRef={markdownRef}
              onCancel={handleCancel}
              onRegenerate={handleRegenerate}
              onUndo={handleUndo}
            />

            {/* 文件修改失败警告 */}
            {!(isLast && loading) && message.fileMutationFailures && message.fileMutationFailures.length > 0 && (
              <FileMutationWarning failures={message.fileMutationFailures} />
            )}

            {/* 完成状态提示 */}
            {!(isLast && loading) && message.completionStatus === 'truncated' && (
              <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-sm">
                <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                <span className="text-amber-700 dark:text-amber-300">{t('message.truncated')}</span>
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
