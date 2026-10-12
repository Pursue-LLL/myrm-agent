/**
 * [INPUT]
 * @/services/memory::IncrementalDiffReportDTO
 * lucide-react::RefreshCw, CheckCircle2, AlertTriangle, ShieldCheck, DatabaseZap
 *
 * [OUTPUT]
 * Component: IncrementalDiffInspectorCard
 *
 * [POS]
 * Diagnostic view presenting incremental chunk diff, hash reuse statistics,
 * and API token savings telemetry. Strictly typed with zero `any`. Single file < 250 lines.
 */

import React from 'react';
import { CheckCircle2, AlertTriangle, ShieldCheck, DatabaseZap } from 'lucide-react';
import type { IncrementalDiffReportDTO } from '@/services/memory';

interface IncrementalDiffInspectorCardProps {
  report: IncrementalDiffReportDTO | null;
  onSimulateEdit: () => void;
  isSimulating: boolean;
}

export const IncrementalDiffInspectorCard: React.FC<
  IncrementalDiffInspectorCardProps
> = ({ report, onSimulateEdit, isSimulating }) => {
  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border">
        <div>
          <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
            <DatabaseZap className="w-4 h-4 text-emerald-500" aria-hidden="true" />
            <span>内容哈希增量索引与 Token 节省遥测</span>
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            基于 Chunk 级别 SHA-256 签名，未修改切片直接复用向量库，免除重复调用 Embedding API
          </p>
        </div>

        <button
          type="button"
          onClick={onSimulateEdit}
          disabled={isSimulating}
          className="px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          {isSimulating ? '增量对比中...' : '模拟增量保存并对比'}
        </button>
      </div>

      {report ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-lg border border-border bg-muted/20">
              <span className="text-xs text-muted-foreground block">总切片数</span>
              <span className="text-lg font-bold font-mono text-foreground mt-0.5 block">
                {report.total_chunks}
              </span>
            </div>

            <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5">
              <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium block">
                复用切片 (免计算)
              </span>
              <span className="text-lg font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-0.5 block">
                {report.reused_chunks}
              </span>
            </div>

            <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
              <span className="text-xs text-amber-600 dark:text-amber-400 font-medium block">
                新增/变更切片
              </span>
              <span className="text-lg font-bold font-mono text-amber-600 dark:text-amber-400 mt-0.5 block">
                {report.changed_chunks}
              </span>
            </div>

            <div className="p-3 rounded-lg border border-border bg-muted/20">
              <span className="text-xs text-muted-foreground block">废弃切片</span>
              <span className="text-lg font-bold font-mono text-foreground mt-0.5 block">
                {report.deleted_chunks}
              </span>
            </div>
          </div>

          <div className="p-4 rounded-xl border border-border bg-muted/30 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground">
                Embedding API 调用节省率 (Token Sparing Ratio):
              </span>
              <span className="font-mono text-sm font-bold text-emerald-600 dark:text-emerald-400">
                {report.token_savings_pct.toFixed(1)}%
              </span>
            </div>

            <progress
              aria-label="Token 节省率"
              value={Math.round(report.token_savings_pct)}
              max={100}
              className="w-full h-2 rounded-full overflow-hidden [&::-webkit-progress-bar]:bg-border [&::-webkit-progress-value]:bg-emerald-500 [&::-moz-progress-bar]:bg-emerald-500"
            />

            <div className="flex items-center gap-2 pt-1 text-[11px] text-muted-foreground">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" aria-hidden="true" />
              <span>
                增量状态：<strong className="text-foreground font-mono">{report.status}</strong>（
                {report.status === 'unchanged'
                  ? '文档内容未变动，实现 100% 向量复用'
                  : report.status === 'partially_updated'
                    ? '局部新增内容已原子化更新，其余历史分块全部复用'
                    : '全量初次索引完成'}
                ）
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="py-6 text-center text-xs text-muted-foreground">
          点击右上角“模拟增量保存并对比”，体验文件被修改时仅对发生差异的切片计算向量的高效节省机制
        </div>
      )}
    </div>
  );
};
