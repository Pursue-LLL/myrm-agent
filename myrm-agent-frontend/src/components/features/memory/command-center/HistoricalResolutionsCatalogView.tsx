/**
 * [INPUT]
 * Props: resolutions, onSelectResolution
 *
 * [OUTPUT]
 * HistoricalResolutionsCatalogView: Catalog table/list of indexed historical failure resolutions.
 *
 * [POS]
 * Secondary view inside FailureSessionRetrievalStudioCard.
 * Direct inspection of historical resolutions and dead-end lessons.
 * Strict typing applied: No `any` types allowed. Single file < 300 lines.
 */

import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertOctagon,
  Copy,
  Terminal,
  Calendar,
  Filter,
} from 'lucide-react';
import type {
  HistoricalResolutionEntryDTO,
  FailureOutcomeType,
} from '@/services/memory/failureSessionRetrieval';

export interface HistoricalResolutionsCatalogViewProps {
  resolutions: HistoricalResolutionEntryDTO[];
}

export const HistoricalResolutionsCatalogView: React.FC<HistoricalResolutionsCatalogViewProps> = ({
  resolutions,
}) => {
  const [filterType, setFilterType] = useState<string>('all');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const filtered = resolutions.filter((item) => {
    if (filterType === 'all') return true;
    return item.outcome_type === filterType;
  });

  return (
    <div className="space-y-4">
      {/* 顶部过滤器与统计 */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-card/60 rounded-lg border border-border">
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">解法类型筛选:</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setFilterType('all')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'all'
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              全部 ({resolutions.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterType('successful_resolution')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'successful_resolution'
                  ? 'bg-emerald-600 text-white font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              正向验证 ({resolutions.filter((r) => r.outcome_type === 'successful_resolution').length})
            </button>
            <button
              type="button"
              onClick={() => setFilterType('cautionary_failure')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                filterType === 'cautionary_failure'
                  ? 'bg-amber-600 text-white font-medium'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              避坑警示 ({resolutions.filter((r) => r.outcome_type === 'cautionary_failure').length})
            </button>
          </div>
        </div>

        <div className="text-xs text-muted-foreground">
          显示 {filtered.length} / {resolutions.length} 条已归档案例
        </div>
      </div>

      {/* 案例列表 */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
            当前筛选条件下暂无历史案例
          </div>
        ) : (
          filtered.map((item) => {
            const isSuccess = item.outcome_type === 'successful_resolution';
            return (
              <div
                key={item.entry_id}
                className={`p-3.5 rounded-lg border transition-all ${
                  isSuccess
                    ? 'bg-emerald-500/[0.03] border-emerald-500/20 hover:border-emerald-500/40'
                    : 'bg-amber-500/[0.03] border-amber-500/20 hover:border-amber-500/40'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                        isSuccess
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                          : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                      }`}
                    >
                      {isSuccess ? (
                        <>
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>验证成功解法</span>
                        </>
                      ) : (
                        <>
                          <AlertOctagon className="w-3.5 h-3.5" />
                          <span>踩坑死胡同警示</span>
                        </>
                      )}
                    </span>

                    <span className="text-xs font-mono font-medium text-foreground">
                      {item.session_id}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      (Turn {item.turn_index})
                    </span>
                  </div>

                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <div className="flex items-center gap-1 text-[11px]">
                      <Calendar className="w-3 h-3" />
                      <span>{item.created_at.slice(0, 10)}</span>
                    </div>
                    <span className="text-[11px] font-medium text-foreground">
                      置信度: {Math.round(item.confidence * 100)}%
                    </span>
                  </div>
                </div>

                {/* 错误指纹摘要 */}
                <div className="mb-2 text-xs text-muted-foreground font-mono bg-muted/40 px-2.5 py-1 rounded">
                  错误匹配特征: {item.error_signature}
                </div>

                {/* 代码段与复制 */}
                <div className="relative group mb-2">
                  <pre
                    className={`p-2.5 rounded bg-background border text-xs font-mono overflow-x-auto ${
                      isSuccess
                        ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                        : 'border-amber-500/30 text-amber-600 dark:text-amber-400'
                    }`}
                  >
                    <code>{item.solution_snippet}</code>
                  </pre>
                  <button
                    type="button"
                    onClick={() => handleCopy(item.solution_snippet, item.entry_id)}
                    className="absolute top-2 right-2 p-1.5 rounded bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
                    title="复制解决方案代码"
                    aria-label="复制解决方案代码"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>

                {copiedId === item.entry_id && (
                  <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium mb-1">
                    已复制解决方案代码到剪贴板
                  </div>
                )}

                {/* 原理阐释 */}
                <p className="text-xs text-foreground/80 leading-relaxed">
                  {item.explanation}
                </p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
