/**
 * Codebase Memory Large Diff Fallback Inspection Card (Item 144).
 * Visual dashboard providing multi-tiered diff volume inspection,
 * noise filtration diagnostics, truncation guards, and topological summaries.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  GitCommit,
  GitPullRequest,
  ShieldAlert,
  ShieldCheck,
  FolderTree,
  Filter,
  RefreshCw,
  Layers,
  FileCode,
  AlertTriangle,
} from 'lucide-react';
import {
  codebaseDiffService,
  DiffFileEntryDTO,
  DiffFallbackVerdictDTO,
} from '@/services/memory/codebaseDiff';

const microScenario: DiffFileEntryDTO[] = [
  { path: 'src/core/pipeline.py', additions: 45, deletions: 12, category: 'core_code' },
  { path: 'tests/test_pipeline.py', additions: 35, deletions: 5, category: 'core_code' },
];

const moderateScenario: DiffFileEntryDTO[] = [
  ...Array.from({ length: 25 }, (_, i) => ({
    path: `src/services/service_${i}.ts`,
    additions: 30,
    deletions: 10,
    category: 'core_code',
  })),
  { path: 'pnpm-lock.yaml', additions: 1200, deletions: 450, category: 'lockfile', is_generated: true },
  { path: 'dist/app.min.js', additions: 400, deletions: 200, category: 'generated', is_generated: true },
  { path: 'assets/hero.svg', additions: 0, deletions: 0, category: 'asset_binary' },
];

const largeScenario: DiffFileEntryDTO[] = Array.from({ length: 140 }, (_, i) => ({
  path: i % 2 === 0 ? `backend/model_${i}.py` : `frontend/view_${i}.tsx`,
  additions: 25,
  deletions: 8,
  category: 'core_code',
}));

export const CodebaseDiffInspectionCard: React.FC = () => {
  const [activeScenario, setActiveScenario] = useState<'micro' | 'moderate' | 'large' | 'massive'>('moderate');
  const [verdict, setVerdict] = useState<DiffFallbackVerdictDTO | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const runEvaluation = useCallback(async (scenarioKey: 'micro' | 'moderate' | 'large' | 'massive') => {
    setIsLoading(true);
    setError(null);
    let files: DiffFileEntryDTO[] = [];
    let declaredTotal: number | undefined;
    let isTruncated = false;

    if (scenarioKey === 'micro') {
      files = microScenario;
    } else if (scenarioKey === 'moderate') {
      files = moderateScenario;
    } else if (scenarioKey === 'large') {
      files = largeScenario;
    } else {
      // Massive scenario with declared count mismatch
      files = Array.from({ length: 20 }, (_, i) => ({
        path: `src/legacy_${i}.c`,
        additions: 15,
        deletions: 5,
        category: 'core_code',
      }));
      declaredTotal = 3200; // API truncated over 3000 cap
      isTruncated = true;
    }

    try {
      const resp = await codebaseDiffService.evaluateDiff({
        files,
        declared_total_files: declaredTotal,
        is_api_truncated: isTruncated,
        commit_message: `feat: sync scenario changes (${scenarioKey})`,
      });
      setVerdict(resp.verdict);
    } catch {
      // Local graceful fallback if backend is offline
      const totalAdd = files.reduce((acc, f) => acc + f.additions, 0);
      const totalDel = files.reduce((acc, f) => acc + f.deletions, 0);
      setVerdict({
        tier: scenarioKey,
        total_files: files.length,
        total_additions: totalAdd,
        total_deletions: totalDel,
        is_truncated: isTruncated,
        truncation_reason: isTruncated ? 'API file list truncated at 3000 cap' : null,
        active_files_count: scenarioKey === 'massive' ? 0 : files.length,
        filtered_noise_files_count: scenarioKey === 'moderate' ? 3 : 0,
        directory_aggregates: [
          { directory: 'src', file_count: files.length, total_additions: totalAdd, total_deletions: totalDel, primary_category: 'core_code' },
        ],
        summary_text: `[Diff Mode: ${scenarioKey.toUpperCase()}] Offline fallback verdict generated.`,
        applied_optimizations: ['client_offline_simulation'],
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    runEvaluation(activeScenario);
  }, [activeScenario, runEvaluation]);

  const getTierBadgeClass = (tier: string) => {
    switch (tier.toLowerCase()) {
      case 'micro':
        return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
      case 'moderate':
        return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20';
      case 'large':
        return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';
      default:
        return 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20';
    }
  };

  return (
    <div
      className="p-5 rounded-xl border border-border bg-card shadow-sm text-card-foreground transition-all space-y-4"
      aria-label="代码库记忆大Diff分级降级检验看板"
    >
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center space-x-2">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <GitPullRequest className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <h3 className="font-semibold text-base leading-tight">
              代码库大 Diff 分级降级诊断
            </h3>
            <p className="text-xs text-muted-foreground">
              对标 codebase-memory #2269 · 四层漏斗自适应降级与 3000 文件截断硬防护
            </p>
          </div>
        </div>
        <button
          onClick={() => runEvaluation(activeScenario)}
          disabled={isLoading}
          aria-label="刷新 Diff 评估诊断"
          className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
        </button>
      </div>

      {/* Scenario Selector */}
      <div className="flex items-center gap-1.5 p-1 rounded-lg bg-muted/50 border border-border/50 text-xs flex-wrap">
        <span className="px-2 text-muted-foreground font-medium">预设场景:</span>
        {(['micro', 'moderate', 'large', 'massive'] as const).map((scKey) => (
          <button
            key={scKey}
            onClick={() => setActiveScenario(scKey)}
            aria-label={`切换到${scKey}场景`}
            className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
              activeScenario === scKey
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {scKey.toUpperCase()}
          </button>
        ))}
      </div>

      {error && (
        <div className="p-3 text-xs rounded-lg bg-destructive/10 text-destructive border border-destructive/20 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Stats Grid */}
      {verdict && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg bg-muted/40 border border-border/40">
            <div className="text-xs text-muted-foreground">执行层级 (Tier)</div>
            <div className="mt-1">
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${getTierBadgeClass(verdict.tier)}`}>
                {verdict.tier.toUpperCase()}
              </span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted/40 border border-border/40">
            <div className="text-xs text-muted-foreground">变更总量</div>
            <div className="mt-1 text-sm font-semibold text-foreground">
              {verdict.total_files} 文件
              <span className="text-xs ml-1 text-emerald-600 dark:text-emerald-400">+{verdict.total_additions}</span>
              <span className="text-xs ml-1 text-rose-600 dark:text-rose-400">-{verdict.total_deletions}</span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted/40 border border-border/40">
            <div className="text-xs text-muted-foreground">噪音折叠</div>
            <div className="mt-1 text-sm font-semibold flex items-center gap-1">
              <Filter className="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true" />
              <span>{verdict.filtered_noise_files_count} 排除</span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted/40 border border-border/40">
            <div className="text-xs text-muted-foreground">截断安全状态</div>
            <div className="mt-1 text-sm font-semibold flex items-center gap-1">
              {verdict.is_truncated ? (
                <>
                  <ShieldAlert className="w-3.5 h-3.5 text-rose-500" aria-hidden="true" />
                  <span className="text-rose-600 dark:text-rose-400 text-xs">已截断降级</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" aria-hidden="true" />
                  <span className="text-emerald-600 dark:text-emerald-400 text-xs">完整保真</span>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Truncation Warning Banner */}
      {verdict?.is_truncated && (
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" aria-hidden="true" />
          <div>
            <span className="font-semibold">触发大 Diff 截断防护：</span>
            <span>{verdict.truncation_reason || '超出处理上限或上游 API 发生截断，已启动拓扑安全保底'}</span>
          </div>
        </div>
      )}

      {/* Directory Clustering Breakdown */}
      {verdict && verdict.directory_aggregates.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <FolderTree className="w-3.5 h-3.5" aria-hidden="true" />
            <span>顶层模块拓扑聚类</span>
          </div>
          <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
            {verdict.directory_aggregates.map((aggr) => (
              <div
                key={aggr.directory}
                className="flex items-center justify-between text-xs p-2 rounded-md bg-muted/30 border border-border/30"
              >
                <div className="flex items-center gap-2 truncate">
                  <FileCode className="w-3.5 h-3.5 text-primary shrink-0" aria-hidden="true" />
                  <span className="font-medium truncate">{aggr.directory}/</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                    {aggr.primary_category}
                  </span>
                </div>
                <div className="text-muted-foreground shrink-0 text-right">
                  <span>{aggr.file_count} 文件 </span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-mono">+{aggr.total_additions}</span>
                  <span className="text-rose-600 dark:text-rose-400 font-mono ml-1">-{aggr.total_deletions}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Safe Context Summary Preview */}
      {verdict?.summary_text && (
        <div
          className="p-2.5 rounded-lg bg-muted/20 border border-border/30 text-xs font-mono text-muted-foreground whitespace-pre-wrap max-h-24 overflow-y-auto"
          aria-label="Diff 降级安全摘要预览"
        >
          {verdict.summary_text}
        </div>
      )}

      {/* Applied Optimizations Pills */}
      {verdict && verdict.applied_optimizations.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap pt-1">
          <Layers className="w-3.5 h-3.5 text-muted-foreground shrink-0" aria-hidden="true" />
          <span className="text-[11px] text-muted-foreground mr-1">激活策略:</span>
          {verdict.applied_optimizations.map((opt) => (
            <span
              key={opt}
              className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground border border-border/50"
            >
              {opt}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
