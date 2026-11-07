/**
 * [INPUT]
 * - ./StepNodeHeader::StepNodeHeader / ./StepErrorPanel::StepErrorPanel / ./StepOutput::* (POS: 节点的头部、错误框与产出)
 * - ./StepTimeline::{StepStatusDot, StepRail} (POS: 状态圆点与连接线)
 * - ./ArchiveRestoreStepAction / ./ArchiveRestoreResultChip / ./SkillManageBatchRollbackAction (POS: 归档恢复与技能撤销入口)
 * - ./treeUtils::TreeNode (POS: 步骤树节点)
 *
 * [OUTPUT]
 * - ProgressStepNode: 步骤树中的一个节点（递归渲染子节点）。
 * - StepNodes: 把同一层的多个节点渲染成列表。
 * - StepNodeContext: 整棵树共享的渲染上下文。
 *
 * [POS]
 * 进度步骤树节点：左侧状态圆点，右侧头部 + 正文（原因、错误框、产出、归档恢复入口、压缩丢弃清单、终端）+ 子节点。
 * 有子节点的计划节点只显示头部与子节点，叶子节点显示完整正文。
 */

import type { TranslateFn } from '@/lib/humanize';
import { cn } from '@/lib/utils/classnameUtils';
import type { ProgressItem } from '@/store/chat/types';
import { ArchiveRestoreResultChip } from './ArchiveRestoreResultChip';
import { ArchiveRestoreStepAction } from './ArchiveRestoreStepAction';
import { SkillManageBatchRollbackAction } from './SkillManageBatchRollbackAction';
import { StepErrorPanel } from './StepErrorPanel';
import { StepNodeHeader } from './StepNodeHeader';
import { StepItemsView, StepTerminal } from './StepOutput';
import { StepRail, StepStatusDot } from './StepTimeline';
import { extractSkillManageBatchId } from './skillManageBatch';
import { getStepVisualState } from './stepTone';
import type { TreeNode } from './treeUtils';

export interface StepNodeContext {
  messageId: string;
  /** Position of the newest step: while the turn is loading, that step is the one in flight. */
  lastIndex: number;
  loading: boolean;
  t: TranslateFn;
  tHumanize: TranslateFn;
  onViewDetail: (step: ProgressItem) => void;
}

interface NodeProps {
  node: TreeNode;
  depth: number;
  ctx: StepNodeContext;
}

/** Most dropped constraints listed before the rest collapses into a count. */
const DROPPED_MANIFEST_LIMIT = 3;

export function ProgressStepNode({ node, depth, ctx }: NodeProps) {
  const { step, originalIndex: index, children } = node;
  const { messageId, lastIndex, loading, t, tHumanize, onViewDetail } = ctx;
  const state = getStepVisualState(step, index === lastIndex && loading);
  const skillBatchId = extractSkillManageBatchId(step);
  const droppedManifest = step.dropped_manifest ?? [];

  return (
    <div className={cn('relative group flex items-start gap-3', depth === 0 ? '-ml-1 pl-1' : 'ml-4 mt-2')}>
      <div className="flex-shrink-0 relative z-10 p-1 -m-1">
        <StepStatusDot state={state} />
      </div>

      <div className="flex flex-col space-y-2 sm:space-y-3 flex-1 min-w-0">
        <StepNodeHeader step={step} state={state} t={t} tHumanize={tHumanize} onViewDetail={onViewDetail} />

        {(!step.is_plan || children.length === 0) && (
          <>
            {step.reason && (
              <p className="text-xs text-muted-foreground italic leading-relaxed whitespace-pre-wrap">{step.reason}</p>
            )}

            <StepErrorPanel step={step} isWarning={state.isWarning} t={t} />
            <StepItemsView step={step} messageId={messageId} index={index} isCurrent={state.isCurrent} />

            {step.archive_restore_actions && step.archive_restore_actions.length > 0 && (
              <ArchiveRestoreStepAction actions={step.archive_restore_actions} block={step.archive_restore_block} />
            )}
            {step.archive_restore_result && <ArchiveRestoreResultChip result={step.archive_restore_result} />}
            {skillBatchId && <SkillManageBatchRollbackAction batchId={skillBatchId} />}

            {droppedManifest.length > 0 && (
              <div className="mt-2 p-2.5 rounded-lg border bg-muted/40 border-border/60">
                <div className="text-[11px] font-medium text-foreground/70 mb-1.5">{t('dropped_manifest_title')}</div>
                <ul className="space-y-1">
                  {droppedManifest.slice(0, DROPPED_MANIFEST_LIMIT).map((item, itemIdx) => (
                    <li
                      key={itemIdx}
                      className="text-[11px] leading-relaxed text-foreground/80 italic break-all whitespace-pre-wrap"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
                {droppedManifest.length > DROPPED_MANIFEST_LIMIT && (
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    {t('dropped_manifest_more', { count: droppedManifest.length - DROPPED_MANIFEST_LIMIT })}
                  </div>
                )}
              </div>
            )}

            <StepTerminal step={step} />
          </>
        )}

        {children.length > 0 && (
          <div className="relative space-y-4 sm:space-y-6 mt-2">
            <StepRail />
            <StepNodes nodes={children} depth={depth + 1} ctx={ctx} />
          </div>
        )}
      </div>
    </div>
  );
}

export function StepNodes({ nodes, depth, ctx }: { nodes: TreeNode[]; depth: number; ctx: StepNodeContext }) {
  return (
    <>
      {nodes.map((node) => (
        <ProgressStepNode key={`${ctx.messageId}-step-${node.originalIndex}`} node={node} depth={depth} ctx={ctx} />
      ))}
    </>
  );
}
