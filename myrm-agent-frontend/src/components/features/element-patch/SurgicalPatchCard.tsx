/* oxlint-disable jsx-a11y/prefer-tag-over-role */
import React from 'react';
import {
  ShieldCheck,
  CheckCircle2,
  Clock,
  Layers,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import { StagedBatchPayload } from './elementPatchTypes';
import {
  calculateBatchResolveSummary,
  formatAnnotationStatus,
} from './elementPatchEngine';
import { useElementPatchStore } from './useElementPatchStore';

export interface SurgicalPatchCardProps {
  batchPayload: StagedBatchPayload;
  onLocateArtifactElement?: (selector: string) => void;
  className?: string;
}

export const SurgicalPatchCard: React.FC<SurgicalPatchCardProps> = ({
  batchPayload,
  onLocateArtifactElement,
  className = '',
}) => {
  const { selectAnnotation, toggleDrawer } = useElementPatchStore();
  const summary = calculateBatchResolveSummary(
    batchPayload.annotations,
    batchPayload.batchId
  );

  const isAllResolved = summary.status === 'all_resolved';

  const handleItemClick = (selector: string, id: string) => {
    selectAnnotation(id);
    toggleDrawer(true);
    if (onLocateArtifactElement) {
      onLocateArtifactElement(selector);
    }
  };

  return (
    <div
      data-testid="surgical-patch-card"
      className={`p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 shadow-xl space-y-3 font-sans ${className}`}
    >
      {/* 1. 头部标题与自愈进度 */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h4 className="text-xs font-bold text-zinc-100">
                工件多元素打包批注
              </h4>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                手术刀式局部补丁
              </span>
            </div>
            <p className="text-[10px] text-zinc-400 font-mono">
              工件 ID: {batchPayload.artifactId} · 批次: {batchPayload.batchId.slice(-8)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold border bg-zinc-950 border-zinc-800 shrink-0">
          {isAllResolved ? (
            <span className="text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> 全部自愈修复 ({summary.resolvedCount}/{summary.totalCount})
            </span>
          ) : (
            <span className="text-indigo-300 flex items-center gap-1">
              <Clock className="w-3 h-3" /> 局部修复中 ({summary.resolvedCount}/{summary.totalCount})
            </span>
          )}
        </div>
      </div>

      {/* 2. 批注清单审查项 */}
      <div className="space-y-1.5 pt-1">
        {batchPayload.annotations.map((ann, idx) => {
          const statusTheme = formatAnnotationStatus(ann.status);
          return (
            // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- clickable card with nested action buttons
            <div
              key={ann.id}
              role="button"
              tabIndex={0}
              onClick={() => {
                handleItemClick(ann.selector, ann.id);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  handleItemClick(ann.selector, ann.id);
                }
              }}
              className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-950/70 border border-zinc-850 hover:border-zinc-750 transition-colors cursor-pointer text-xs group"
            >
              <div className="flex items-center gap-2 truncate pr-2">
                <span className="w-4 h-4 rounded-full bg-zinc-800 text-zinc-300 text-[10px] font-bold font-mono flex items-center justify-center shrink-0 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                  {idx + 1}
                </span>
                <span className="font-mono text-zinc-200 font-semibold truncate max-w-[140px]">
                  {ann.selector}
                </span>
                <span className="text-zinc-400 truncate max-w-[200px]">
                  {ann.instruction}
                </span>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${statusTheme.bg} ${statusTheme.text} ${statusTheme.border}`}
                >
                  {statusTheme.label}
                </span>
                <ChevronRight className="w-3.5 h-3.5 text-zinc-500 group-hover:text-zinc-300 transition-colors" />
              </div>
            </div>
          );
        })}
      </div>

      {/* 3. 底部防随机漂移保证 */}
      <div className="flex items-center justify-between pt-1 border-t border-zinc-850 text-[10px] text-zinc-500 font-mono">
        <span className="flex items-center gap-1">
          <Sparkles className="w-3 h-3 text-indigo-400" />
          <span>AST 选择器级精准替换 · 页面其余组件 100% 保持不变</span>
        </span>
        <span>已注入 &lt;surgical_patch_scope&gt;</span>
      </div>
    </div>
  );
};
