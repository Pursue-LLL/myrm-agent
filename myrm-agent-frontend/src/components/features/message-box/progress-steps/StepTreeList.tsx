/**
 * [INPUT]
 * - ./ProgressStepNode::{StepNodes, StepNodeContext} (POS: 步骤树节点)
 * - ./treeUtils::{foldRoots, TreeNode} (POS: 折叠规则 SSOT)
 *
 * [OUTPUT]
 * - StepTreeList: 展开面板里的顶层步骤列表，步骤过多时折叠中段。
 *
 * [POS]
 * 进度步骤的顶层列表：折叠规则取自 `foldRoots`；折叠时保留头尾并给出「展开 N 个中间步骤」入口，
 * 展开后给出「收起」入口。入口按钮不向外冒泡，避免触发面板自身的点击展开。
 */

import { ChevronUp, Layers } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { StepNodes, type StepNodeContext } from './ProgressStepNode';
import { foldRoots, type TreeNode } from './treeUtils';

interface StepTreeListProps {
  roots: TreeNode[];
  showAll: boolean;
  onShowAllChange: (showAll: boolean) => void;
  ctx: StepNodeContext;
}

export function StepTreeList({ roots, showAll, onShowAllChange, ctx }: StepTreeListProps) {
  const { t } = ctx;
  const foldable = foldRoots(roots);

  if (!foldable || showAll) {
    return (
      <>
        <StepNodes nodes={roots} depth={0} ctx={ctx} />
        {foldable && showAll && (
          <div className="relative mt-3 pl-8">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onShowAllChange(false);
              }}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted/30 hover:bg-muted/60 border border-border/40 text-xs text-muted-foreground hover:text-foreground transition-all duration-200"
            >
              <ChevronUp className="w-3.5 h-3.5" />
              {t('folding.showLess')}
            </button>
          </div>
        )}
      </>
    );
  }

  const { head, folded, tail } = foldable;

  return (
    <>
      <StepNodes nodes={head} depth={0} ctx={ctx} />

      <div className="relative my-3 pl-8">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onShowAllChange(true);
          }}
          className="group/fold w-full flex items-center justify-between px-3.5 py-2 rounded-xl bg-muted/40 hover:bg-muted/70 border border-border/50 text-xs text-muted-foreground hover:text-foreground transition-all duration-200"
        >
          <span className="flex items-center gap-2 font-medium">
            <Layers className="w-3.5 h-3.5 text-primary/70 group-hover/fold:text-primary transition-colors" />
            {t('folding.showMore', { count: folded.length })}
          </span>
          <Badge variant="outline" className="text-[10px] font-mono h-5 px-2 bg-background/50 border-border/40">
            {t('folding.stepSummary', { completed: folded.length, total: roots.length })}
          </Badge>
        </button>
      </div>

      <StepNodes nodes={tail} depth={0} ctx={ctx} />
    </>
  );
}
