'use client';

/**
 * [INPUT]
 * @/services/memory/diskReconciliation::ReconciliationReportDTO, FtsReconciledHitDTO, TriggerReconciliationRequestDTO
 *
 * [OUTPUT]
 * DiskReconciliationAuditConsoleView: Subview component rendering bi-directional reconciliation controls,
 * audit reports (Direction A indexing & Direction B dead-row pruning), and FTS verification search.
 *
 * [POS]
 * Subcomponent for Item 94 (Disk Memory FTS Reconciliation Loop and Explicit Write Gate Suite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { RefreshCw, Search, FileText, Trash2, CheckCircle2, ArrowRightLeft, FolderSync } from 'lucide-react';
import type {
  ReconciliationReportDTO,
  FtsReconciledHitDTO,
  TriggerReconciliationRequestDTO,
} from '@/services/memory/diskReconciliation';

interface DiskReconciliationAuditConsoleViewProps {
  lastReport: ReconciliationReportDTO | null;
  onTriggerReconciliation: (request: TriggerReconciliationRequestDTO) => Promise<void>;
  onSearchFts: (query: string) => Promise<void>;
  searchResults: FtsReconciledHitDTO[];
}

export function DiskReconciliationAuditConsoleView({
  lastReport,
  onTriggerReconciliation,
  onSearchFts,
  searchResults,
}: DiskReconciliationAuditConsoleViewProps): React.JSX.Element {
  const [rootsInput, setRootsInput] = useState<string>('.myrm/memory');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [isSearching, setIsSearching] = useState<boolean>(false);

  const handleSyncSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSyncing(true);
    try {
      const parsedRoots = rootsInput
        .split(',')
        .map((r) => r.trim())
        .filter(Boolean);
      await onTriggerReconciliation({
        roots: parsedRoots.length > 0 ? parsedRoots : ['.myrm/memory'],
      });
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      return;
    }
    setIsSearching(true);
    try {
      await onSearchFts(searchQuery.trim());
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="disk-reconciliation-audit-console-view">
      {/* Overview Banner */}
      <div className="rounded-lg border border-border/60 bg-accent/15 p-3 text-xs space-y-1.5">
        <div className="font-semibold text-foreground flex items-center gap-1.5">
          <ArrowRightLeft className="w-4 h-4 text-primary" />
          磁盘文件与 SQLite FTS5 双向对账机制 (Bi-Directional Loop)
        </div>
        <p className="text-muted-foreground leading-relaxed text-[11px]">
          解决用户在外部编辑器修改/删除 Markdown 笔记或 Git 切换分支导致索引脱节的痛点：
          <span className="text-foreground font-medium"> 方向 A</span>（哈希指纹建索）自动同步新增与变更文件；
          <span className="text-foreground font-medium"> 方向 B</span>（僵尸记录裁剪）自动清理已删除文件死记录，杜绝幽灵脏读。
        </p>
      </div>

      {/* Main Grid: Sync Trigger Form & Last Audit Report */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left: Trigger Reconciliation Loop */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
            <FolderSync className="w-4 h-4 text-primary" />
            触发双向对账巡检 (Trigger Reconcile)
          </div>

          <form onSubmit={handleSyncSubmit} className="space-y-2 text-xs" data-testid="reconciliation-sync-form">
            <div>
              <label htmlFor="reconcile-roots-input" className="block text-muted-foreground mb-1 text-[11px]">
                扫描目标磁盘目录（逗号分隔相对或绝对路径）：
              </label>
              <input
                id="reconcile-roots-input"
                type="text"
                value={rootsInput}
                onChange={(e) => setRootsInput(e.target.value)}
                placeholder=".myrm/memory, docs/decisions"
                className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-xs text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="flex justify-end pt-1">
              <Button
                type="submit"
                size="sm"
                disabled={isSyncing}
                aria-label="立即执行双向对账巡检"
                className="text-xs focus:outline-none focus:ring-2 focus:ring-primary flex items-center gap-1.5"
                data-testid="btn-trigger-reconcile"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
                {isSyncing ? '正在对账中...' : '立即执行双向对账'}
              </Button>
            </div>
          </form>

          {/* FTS Verification Search Bar */}
          <div className="pt-2 border-t border-border/40 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Search className="w-3.5 h-3.5 text-primary" />
              FTS5 全文索引一致性检索验证
            </div>
            <form onSubmit={handleSearchSubmit} className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="输入检索词检验 FTS 命中..."
                aria-label="输入检索词"
                className="flex-1 rounded border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <Button
                type="submit"
                size="sm"
                variant="outline"
                disabled={isSearching || !searchQuery.trim()}
                aria-label="执行全文检索"
                className="text-xs h-7 focus:outline-none focus:ring-2 focus:ring-primary"
                data-testid="btn-reconciliation-search"
              >
                {isSearching ? '检索中' : '检索'}
              </Button>
            </form>
          </div>
        </div>

        {/* Right: Last Reconciliation Audit Report */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              最新对账审计报告 (Latest Audit Report)
            </span>
            {lastReport && (
              <span className="font-mono text-[10px] text-muted-foreground">{lastReport.reconcile_id}</span>
            )}
          </div>

          {lastReport ? (
            <div className="space-y-2 text-xs" data-testid="reconciliation-report-box">
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded border border-border/50 bg-background/60 p-2">
                  <span className="text-muted-foreground block text-[10px]">磁盘物理文件扫描</span>
                  <span className="text-sm font-bold text-foreground font-mono" data-testid="report-scanned-count">
                    {lastReport.scanned_disk_files_count} 篇
                  </span>
                </div>
                <div className="rounded border border-border/50 bg-background/60 p-2">
                  <span className="text-muted-foreground block text-[10px]">方向 A: 增量建索与更新</span>
                  <span className="text-sm font-bold text-emerald-600 font-mono" data-testid="report-indexed-count">
                    +{lastReport.indexed_or_updated_count} 条
                  </span>
                </div>
                <div className="rounded border border-border/50 bg-background/60 p-2">
                  <span className="text-muted-foreground block text-[10px]">方向 B: 僵尸死记录修剪</span>
                  <span className="text-sm font-bold text-amber-600 font-mono" data-testid="report-pruned-count">
                    -{lastReport.pruned_dead_rows_count} 条
                  </span>
                </div>
                <div className="rounded border border-border/50 bg-background/60 p-2">
                  <span className="text-muted-foreground block text-[10px]">对账巡检耗时</span>
                  <span className="text-sm font-bold text-primary font-mono" data-testid="report-duration-ms">
                    {lastReport.duration_ms.toFixed(1)} ms
                  </span>
                </div>
              </div>

              <div className="rounded bg-background/50 border border-border/40 p-2 flex items-center justify-between text-[11px]">
                <span className="text-muted-foreground">执行状态：</span>
                <Badge
                  variant={lastReport.status === 'completed' ? 'default' : 'destructive'}
                  className="text-[10px]"
                >
                  {lastReport.status}
                </Badge>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-muted-foreground">
              尚未执行对账，可点击左侧按钮立即巡检磁盘文件。
            </div>
          )}
        </div>
      </div>

      {/* FTS Search Hits Console */}
      {searchResults.length > 0 && (
        <div className="rounded-lg border border-border/60 bg-accent/10 p-3 space-y-2">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-primary" />
              FTS5 检索命中结果 ({searchResults.length} 条)
            </span>
          </div>

          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1" data-testid="reconciliation-search-hits-list">
            {searchResults.map((hit) => (
              <div
                key={hit.file_path}
                className="rounded border border-border/50 bg-background/70 p-2 text-xs space-y-0.5"
                data-testid={`fts-hit-item-${hit.file_path}`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground">{hit.title}</span>
                  <Badge variant="outline" className="text-[10px] font-mono">
                    Score: {hit.rank_score.toFixed(3)}
                  </Badge>
                </div>
                <div className="font-mono text-[10px] text-muted-foreground truncate">{hit.file_path}</div>
                <p
                  className="text-[11px] text-muted-foreground line-clamp-2 pt-0.5"
                  dangerouslySetInnerHTML={{ __html: hit.snippet }}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
