'use client';

/**
 * [INPUT]
 * @/services/memory/procedureExperience::DualNodeRetrievalRequest, DualNodeRetrievalResponseDTO,
 *   RetrievalNodeKind, ProcedureMemoryEntryDTO
 *
 * [OUTPUT]
 * DualNodeRetrievalConsoleView: Subview providing fixed-count dual-node retrieval testing,
 * first-user intent vs pre-write intercept node routing, and anchor surface matching metrics.
 *
 * [POS]
 * Subcomponent for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Search,
  GitPullRequest,
  Sliders,
  ShieldCheck,
  ShieldAlert,
  ArrowRight,
  Zap,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';
import type {
  DualNodeRetrievalRequest,
  DualNodeRetrievalResponseDTO,
  RetrievalNodeKind,
} from '@/services/memory/procedureExperience';

interface DualNodeRetrievalConsoleViewProps {
  onRetrieve: (req: DualNodeRetrievalRequest) => Promise<DualNodeRetrievalResponseDTO>;
  isLoading: boolean;
}

export function DualNodeRetrievalConsoleView({
  onRetrieve,
  isLoading,
}: DualNodeRetrievalConsoleViewProps): React.JSX.Element {
  const [nodeKind, setNodeKind] = useState<RetrievalNodeKind>('first_user');
  const [queryText, setQueryText] = useState<string>('在主分支发布应用并做门禁检查');
  const [topN, setTopN] = useState<number>(2);
  const [retrievalResult, setRetrievalResult] = useState<DualNodeRetrievalResponseDTO | null>(null);
  const [searching, setSearching] = useState<boolean>(false);

  const presets = [
    {
      label: '生产发布门禁 (首问)',
      node: 'first_user' as RetrievalNodeKind,
      query: '在主分支发布应用并做门禁检查',
      top: 2,
    },
    {
      label: '数据库写前隔离 (写前)',
      node: 'pre_write' as RetrievalNodeKind,
      query: '在写数据库前进行租户隔离检查',
      top: 1,
    },
    {
      label: '代码严格重构 (写前)',
      node: 'pre_write' as RetrievalNodeKind,
      query: '执行严格重构，避免 any 类型，保护公共 API',
      top: 1,
    },
  ];

  const handleExecuteRetrieve = async (overrideQuery?: string, overrideNode?: RetrievalNodeKind, overrideTop?: number) => {
    const q = overrideQuery ?? queryText;
    const n = overrideNode ?? nodeKind;
    const t = overrideTop ?? topN;
    if (!q.trim()) return;

    setSearching(true);
    try {
      const res = await onRetrieve({
        query_text: q.trim(),
        node_kind: n,
        top_n: t,
      });
      setRetrievalResult(res);
    } finally {
      setSearching(false);
    }
  };

  const handleApplyPreset = (p: typeof presets[number]) => {
    setQueryText(p.query);
    setNodeKind(p.node);
    setTopN(p.top);
    void handleExecuteRetrieve(p.query, p.node, p.top);
  };

  return (
    <div className="space-y-4">
      {/* Console Input and Settings */}
      <div className="rounded-xl border border-border-subtle bg-surface p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <GitPullRequest className="h-4 w-4" />
            </div>
            <div>
              <span className="font-semibold text-text-primary text-xs">
                固定条数双节点检索控制台 (Fixed-Count Dual-Node Retrieval)
              </span>
              <p className="text-text-secondary text-[11px]">
                首问意图（First-User）+ 写前拦截（Pre-Write）双节点命中，固定 Top-N 彻底终结字符截断
              </p>
            </div>
          </div>

          {/* Quick Presets */}
          <div className="flex flex-wrap items-center gap-1.5">
            {presets.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => handleApplyPreset(p)}
                className="rounded-md border border-border-subtle bg-surface-subtle px-2 py-1 text-[11px] text-text-secondary hover:text-text-primary hover:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary"
                aria-label={`预设: ${p.label}`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Node Kind and Top N Selection */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 border-t border-border-subtle/60 pt-3">
          <div>
            <label htmlFor="node-kind-select" className="block text-xs font-medium text-text-secondary mb-1">
              拦截节点位置 (Node Kind)
            </label>
            <div className="flex rounded-lg border border-border-subtle bg-surface-subtle p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setNodeKind('first_user')}
                className={`flex-1 rounded-md py-1 transition-colors text-center focus:outline-none focus:ring-2 focus:ring-primary ${
                  nodeKind === 'first_user'
                    ? 'bg-surface font-semibold text-text-primary shadow-xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                首问意图 (first_user)
              </button>
              <button
                type="button"
                onClick={() => setNodeKind('pre_write')}
                className={`flex-1 rounded-md py-1 transition-colors text-center focus:outline-none focus:ring-2 focus:ring-primary ${
                  nodeKind === 'pre_write'
                    ? 'bg-surface font-semibold text-text-primary shadow-xs'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                写前拦截 (pre_write)
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="top-n-select" className="block text-xs font-medium text-text-secondary mb-1">
              固定条数 (Fixed Top-N)
            </label>
            <select
              id="top-n-select"
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              className="w-full rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value={1}>Top 1 条 (高精度单点拦截)</option>
              <option value={2}>Top 2 条 (首问推荐默认值)</option>
              <option value={4}>Top 4 条 (复合任务多策略)</option>
            </select>
          </div>

          <div className="flex items-end">
            <Button
              type="button"
              onClick={() => void handleExecuteRetrieve()}
              disabled={isLoading || searching || !queryText.trim()}
              className="w-full bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary flex items-center justify-center gap-1.5"
            >
              <Search className={`h-3.5 w-3.5 ${searching ? 'animate-spin' : ''}`} />
              <span>{searching ? '检索中...' : '执行双节点检索'}</span>
            </Button>
          </div>
        </div>

        {/* Query Input */}
        <div>
          <label htmlFor="retrieval-query-input" className="block text-xs font-medium text-text-secondary mb-1">
            检索意图查询 (Query Text)
          </label>
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-tertiary" />
            <input
              id="retrieval-query-input"
              type="text"
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              placeholder="输入任务描述或写操作上下文..."
              className="w-full rounded-lg border border-border-subtle bg-surface-subtle pl-9 pr-3 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      </div>

      {/* Retrieval Results */}
      {retrievalResult && (
        <div className="rounded-xl border border-border-subtle bg-surface p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-text-primary text-xs">
                检索命中结果 ({retrievalResult.matched_entries.length} / Top-{retrievalResult.top_n_requested})
              </span>
              <Badge variant="outline" className="bg-primary/10 text-primary text-[10px]">
                节点: {retrievalResult.node_kind}
              </Badge>
            </div>
            <span className="text-[11px] text-text-secondary">
              固定条数注入保证 · 零字符预算折损
            </span>
          </div>

          {retrievalResult.matched_entries.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border-subtle p-6 text-center text-text-secondary text-xs">
              未命中任何过程形态经验，请尝试调整查询词或切换节点位置。
            </div>
          ) : (
            <div className="space-y-3">
              {retrievalResult.matched_entries.map((item) => (
                <div
                  key={item.entry_id}
                  className="rounded-lg border border-border-subtle bg-surface-subtle/50 p-3 space-y-2"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h5 className="font-semibold text-text-primary text-xs">{item.name}</h5>
                      <p className="text-text-secondary text-[11px] mt-0.5">{item.operation_intent}</p>
                    </div>
                    <span className="font-mono text-emerald-600 text-xs font-semibold">
                      置信度: {(item.confidence * 100).toFixed(0)}%
                    </span>
                  </div>

                  {/* Compact retrieval anchor */}
                  <div className="rounded bg-surface px-2 py-1 font-mono text-[10px] text-text-secondary border border-border-subtle truncate">
                    <span className="text-primary font-medium">检索锚点: </span>
                    {item.retrieval_anchor}
                  </div>

                  {/* Anti-patterns & Boundaries (Crucial for pre-write) */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs pt-1">
                    <div className="rounded border border-amber-300/40 bg-amber-500/5 p-2 space-y-1">
                      <span className="font-medium text-amber-700 text-[10px] flex items-center gap-1">
                        <ShieldAlert className="h-3 w-3" />
                        写前不可变边界
                      </span>
                      <ul className="text-text-secondary text-[10px] space-y-0.5 list-disc list-inside">
                        {item.immutable_boundary.slice(0, 2).map((b, idx) => (
                          <li key={idx} className="truncate">{b}</li>
                        ))}
                      </ul>
                    </div>

                    <div className="rounded border border-rose-300/40 bg-rose-500/5 p-2 space-y-1">
                      <span className="font-medium text-rose-700 text-[10px] flex items-center gap-1">
                        <ShieldAlert className="h-3 w-3" />
                        写前反模式避坑
                      </span>
                      <ul className="text-text-secondary text-[10px] space-y-0.5 list-disc list-inside">
                        {item.anti_patterns.slice(0, 2).map((a, idx) => (
                          <li key={idx} className="truncate">{a}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
