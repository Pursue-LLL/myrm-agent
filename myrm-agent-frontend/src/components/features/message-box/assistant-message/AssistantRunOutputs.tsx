'use client';

/**
 * [INPUT]
 * @/store/chat/types::Message (POS: Chat message model)
 * ./messagePayloads (POS: Typed readers of the loosely typed message payload)
 * ./GeneratedMediaCards (POS: Cards of the images, videos and speech the turn generated)
 * ../progress-steps/ProgressSteps (POS: Collapsible Task Steps tree)
 * @/components/features/chat-window/{ExecutionPhaseStepper,EvidenceStageHUD,CouncilResultCard,approval/VisualApprovalInlineSection} (POS: Turn-level run panels)
 * @/components/features/artifacts/{ArtifactsDisplay,ArtifactErrorBoundary} (POS: Generated artifacts and their render boundary)
 *
 * [OUTPUT]
 * AssistantRunOutputs: Everything a turn produced besides the answer text, in the order it is shown above the answer.
 *
 * [POS]
 * Run outputs of one assistant message: analysis status, progress and phase, consensus and council panels, artifacts,
 * images, recordings, MCP apps, and the generated-media / scheduled-job / kanban cards. It renders into the column of
 * the bubble as siblings of the answer block, so it returns a fragment and adds no wrapper of its own.
 */

import { useTranslations } from 'next-intl';
import type { Message } from '@/store/chat/types';
import ArtifactErrorBoundary from '@/components/features/artifacts/ArtifactErrorBoundary';
import ArtifactsDisplay from '@/components/features/artifacts/ArtifactsDisplay';
import VisualApprovalInlineSection from '@/components/features/chat-window/approval/VisualApprovalInlineSection';
import { CouncilResultCard } from '@/components/features/chat-window/CouncilResultCard';
import { EvidenceStageHUD } from '@/components/features/chat-window/EvidenceStageHUD';
import { ExecutionPhaseStepper } from '@/components/features/chat-window/ExecutionPhaseStepper';
import ConsensusThinkingPanel from '../ConsensusThinkingPanel';
import { CronJobSystemCard } from '../CronJobSystemCard';
import { KanbanTaskCreatedCard } from '../KanbanTaskCreatedCard';
import { McpAppSection } from '../McpAppSection';
import ProgressSteps from '../progress-steps/ProgressSteps';
import { messageHasSkillManageUndo } from '../progress-steps/skillManageBatch';
import SessionRecordingCard from '../SessionRecordingCard';
import { SkillManageUndoHintCard } from '../SkillManageUndoHintCard';
import ToolImageGallery from '../ToolImageGallery';
import { GeneratedMediaCards } from './GeneratedMediaCards';
import {
  readCronJobResult,
  readKanbanTasksCreated,
  readMcpApps,
  readMediaGenerated,
  readSessionRecording,
  readToolImages,
  resolveProgressSteps,
} from './messagePayloads';

export function AssistantRunOutputs({
  message,
  loading,
  isLast,
  chatId,
  approvalPending,
}: {
  message: Message;
  loading: boolean;
  isLast: boolean;
  chatId: string | undefined;
  /** A tool approval is waiting on this message. */
  approvalPending: boolean;
}) {
  const t = useTranslations('chat');
  const tProgress = useTranslations('progressSteps');
  const progressSteps = resolveProgressSteps(message);
  const toolImages = readToolImages(message);
  const mcpApps = readMcpApps(message);
  const sessionRecording = readSessionRecording(message);
  const cronJobResult = readCronJobResult(message);
  const kanbanTasksCreated = readKanbanTasksCreated(message);
  const mediaGenerated = readMediaGenerated(message);

  return (
    <>
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
      <div className="space-y-1.5">
        {(message.phaseExecution || (loading && isLast)) && (
          <ExecutionPhaseStepper
            phaseExecution={message.phaseExecution}
            phaseHistory={message.phaseHistory}
            loading={loading && isLast}
            isApprovalPending={approvalPending}
          />
        )}
        {progressSteps.length > 0 && (
          <>
            <EvidenceStageHUD steps={progressSteps} loading={loading} />
            <ProgressSteps messageId={message.messageId} steps={progressSteps} loading={loading} />
            {messageHasSkillManageUndo(progressSteps) && !(loading && isLast) ? (
              <SkillManageUndoHintCard messageId={message.messageId} />
            ) : null}
          </>
        )}
      </div>

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
      {sessionRecording ? (
        <SessionRecordingCard filename={sessionRecording.filename} previewUrl={sessionRecording.preview_url} />
      ) : null}

      {/* MCP Apps (ext-apps) 嵌入式 UI */}
      {mcpApps.length > 0 && (
        <ArtifactErrorBoundary fallbackMessage={t('mcpAppRenderFailed')}>
          <McpAppSection views={mcpApps} />
        </ArtifactErrorBoundary>
      )}

      {/* 生成的图像 / 视频 / 语音：由媒体工具登记，卡片不依赖模型回复文字 */}
      {mediaGenerated.length > 0 && <GeneratedMediaCards entries={mediaGenerated} />}

      {/* 定时任务创建/更新卡片 */}
      {cronJobResult ? <CronJobSystemCard result={cronJobResult} /> : null}

      {/* Kanban 任务创建卡片 */}
      {kanbanTasksCreated.length > 0 && chatId
        ? kanbanTasksCreated.map((item) => <KanbanTaskCreatedCard key={item.task_id} result={item} chatId={chatId} />)
        : null}
    </>
  );
}
