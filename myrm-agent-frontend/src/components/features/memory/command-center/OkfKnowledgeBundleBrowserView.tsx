'use client';

/**
 * [INPUT]
 * @/services/memory/gitOkf::ConceptSummaryItemDTO, OKFConceptDetailDTO, LoadBundleRequestDTO
 *
 * [OUTPUT]
 * OkfKnowledgeBundleBrowserView: Subview component rendering OKF v0.2 bundle loading,
 * phase 1 lightweight progressive disclosure concept list (<300 tokens), governance filter,
 * and phase 2 deep concept inspection panel.
 *
 * [POS]
 * Subcomponent for Item 95 (Git-Native Project Knowledge Bundle & Memory Rot Prevention Suite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { BookOpen, FolderGit2, AlertTriangle, CheckCircle, ShieldAlert, Code2, ArrowRight } from 'lucide-react';
import type {
  ConceptSummaryItemDTO,
  OKFConceptDetailDTO,
  LoadBundleRequestDTO,
} from '@/services/memory/gitOkf';

interface OkfKnowledgeBundleBrowserViewProps {
  concepts: ConceptSummaryItemDTO[];
  selectedDetail: OKFConceptDetailDTO | null;
  onLoadBundle: (request: LoadBundleRequestDTO) => Promise<void>;
  onSelectConcept: (conceptId: string) => Promise<void>;
}

export function OkfKnowledgeBundleBrowserView({
  concepts,
  selectedDetail,
  onLoadBundle,
  onSelectConcept,
}: OkfKnowledgeBundleBrowserViewProps): React.JSX.Element {
  const [bundlePathInput, setBundlePathInput] = useState<string>('.myrm/knowledge');
  const [governanceFilter, setGovernanceFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleLoadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bundlePathInput.trim()) {
      return;
    }
    setIsLoading(true);
    try {
      await onLoadBundle({ bundle_path: bundlePathInput.trim() });
    } finally {
      setIsLoading(false);
    }
  };

  const filteredConcepts = concepts.filter((c) => {
    if (governanceFilter === 'all') {
      return true;
    }
    return c.governance === governanceFilter;
  });

  return (
    <div className="space-y-4" data-testid="okf-knowledge-bundle-browser-view">
      {/* Bundle Loader Bar */}
      <div className="rounded-lg border border-border/60 bg-accent/15 p-3 text-xs space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-foreground flex items-center gap-1.5">
            <FolderGit2 className="w-4 h-4 text-primary" />
            Git 原生知识包挂载 (Mount OKF v0.2 Bundle)
          </span>
          <span className="text-muted-foreground text-[11px]">随 Git 分支与 PR 无损协同流转</span>
        </div>

        <form onSubmit={handleLoadSubmit} className="flex gap-2" data-testid="load-bundle-form">
          <input
            type="text"
            value={bundlePathInput}
            onChange={(e) => setBundlePathInput(e.target.value)}
            placeholder="知识包目录路径，例如：.myrm/knowledge 或 knowledge"
            aria-label="知识包目录路径"
            className="flex-1 rounded border border-border bg-background px-2.5 py-1.5 text-xs text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <Button
            type="submit"
            size="sm"
            disabled={isLoading || !bundlePathInput.trim()}
            aria-label="加载并重构知识包索引"
            className="text-xs focus:outline-none focus:ring-2 focus:ring-primary"
            data-testid="btn-load-bundle"
          >
            {isLoading ? '加载中...' : '加载知识包'}
          </Button>
        </form>
      </div>

      {/* Filter and Summary Banner */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="text-muted-foreground text-[11px]">
          第一阶段渐进式披露：仅拉取轻量卡片索引（&lt;300 Tokens 脚印），节省 80%+ 上下文开销
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground text-[11px]">治理层级：</span>
          <select
            value={governanceFilter}
            onChange={(e) => setGovernanceFilter(e.target.value)}
            aria-label="按治理层级筛选"
            className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="all">全部概念 ({concepts.length})</option>
            <option value="constraint">强制约束 (constraint)</option>
            <option value="hold">人工签署 (hold)</option>
            <option value="context">背景知识 (context)</option>
          </select>
        </div>
      </div>

      {/* Main Grid: Phase 1 Cards List & Phase 2 Detail Inspector */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Left: Phase 1 Progressive Disclosure Concept Cards */}
        <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
          {filteredConcepts.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/70 p-6 text-center text-xs text-muted-foreground">
              当前目录下无匹配 OKF 概念卡片，请点击上方加载有效知识包。
            </div>
          ) : (
            filteredConcepts.map((concept) => {
              const isSelected = selectedDetail?.id === concept.id;
              return (
                <button
                  type="button"
                  key={concept.id}
                  onClick={() => onSelectConcept(concept.id)}
                  aria-label={`检视知识卡片 ${concept.title}`}
                  className={`w-full text-left rounded-lg border p-2.5 transition-colors text-xs focus:outline-none focus:ring-2 focus:ring-primary ${
                    isSelected
                      ? 'border-primary bg-primary/10'
                      : 'border-border/60 bg-accent/20 hover:bg-accent/40'
                  }`}
                  data-testid={`concept-card-${concept.id}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-foreground truncate">{concept.title}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      {concept.is_stale && (
                        <Badge variant="destructive" className="text-[9px] px-1.5 py-0 flex items-center gap-0.5">
                          <AlertTriangle className="w-2.5 h-2.5" />
                          STALE 过期
                        </Badge>
                      )}
                      <Badge
                        variant={concept.governance === 'constraint' ? 'default' : 'outline'}
                        className="text-[9px] uppercase font-mono"
                      >
                        {concept.governance}
                      </Badge>
                    </div>
                  </div>

                  <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                    {concept.description || '暂无描述内容'}
                  </p>

                  <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                    <span className="truncate max-w-[200px]">{concept.id}</span>
                    {concept.code_refs.length > 0 && (
                      <span className="flex items-center gap-0.5 text-primary/80">
                        <Code2 className="w-3 h-3" />
                        {concept.code_refs.length} refs
                      </span>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Right: Phase 2 Detailed Inspection Panel */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <BookOpen className="w-4 h-4 text-primary" />
              第二阶段完整卡片检视 (Deep Inspection)
            </span>
            {selectedDetail && (
              <span className="font-mono text-[10px] text-muted-foreground">{selectedDetail.id}</span>
            )}
          </div>

          {selectedDetail ? (
            <div className="space-y-2.5 text-xs" data-testid="concept-detail-box">
              <div className="space-y-1">
                <div className="text-sm font-bold text-foreground flex items-center justify-between">
                  <span>{selectedDetail.title}</span>
                  <Badge variant="outline" className="text-[10px] uppercase font-mono">
                    {selectedDetail.governance}
                  </Badge>
                </div>
                <div className="text-muted-foreground text-[11px]">{selectedDetail.description}</div>
              </div>

              {/* Shelf-Life Staleness Alert */}
              {selectedDetail.is_stale && (
                <div className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-800 dark:text-amber-300 flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-amber-500 shrink-0" />
                  <span>
                    记忆防腐烂门禁拦截：该卡片已于 {selectedDetail.stale_after} 超过显式保质期，严防过时规范误导 Agent。
                  </span>
                </div>
              )}

              {/* Code Refs */}
              {selectedDetail.code_refs.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[11px] text-muted-foreground font-medium">代码关联路径 (code_refs):</span>
                  <div className="flex flex-wrap gap-1">
                    {selectedDetail.code_refs.map((ref) => (
                      <span
                        key={ref}
                        className="rounded bg-background/80 border border-border/60 px-1.5 py-0.5 text-[10px] font-mono text-foreground"
                      >
                        {ref}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Markdown Body */}
              <div className="space-y-1 pt-1 border-t border-border/40">
                <span className="text-[11px] text-muted-foreground font-medium">正文规范细节 (Body Content):</span>
                <div
                  className="rounded border border-border/50 bg-background/80 p-2.5 max-h-48 overflow-y-auto text-[11px] leading-relaxed font-mono whitespace-pre-wrap text-foreground"
                  data-testid="concept-body-content"
                >
                  {selectedDetail.body || '无正文细节'}
                </div>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-muted-foreground">
              请从左侧选择一张知识卡片以检视完整规范细节。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
