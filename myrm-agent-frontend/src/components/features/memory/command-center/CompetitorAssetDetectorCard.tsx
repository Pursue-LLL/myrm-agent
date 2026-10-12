/**
 * Competitor Asset Detector Card.
 * Scans local disk and displays discovered competitor memory files with quick-select actions.
 */

import React from 'react';
import {
  FileText,
  FolderSearch,
  CheckCircle2,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import type {
  DetectedCandidateDTO,
  MigrationSourceType,
} from '@/services/memory/memoryMigration';

interface CompetitorAssetDetectorCardProps {
  candidates: DetectedCandidateDTO[];
  isScanning: boolean;
  selectedPath?: string;
  onSelectCandidate: (candidate: DetectedCandidateDTO) => void;
  onCustomScan: (customPath: string) => void;
}

export const CompetitorAssetDetectorCard: React.FC<CompetitorAssetDetectorCardProps> = ({
  candidates,
  isScanning,
  selectedPath,
  onSelectCandidate,
  onCustomScan,
}) => {
  const [customInput, setCustomInput] = React.useState('');

  const getSourceBadge = (source: MigrationSourceType) => {
    switch (source) {
      case 'openclaw':
        return (
          <span className="inline-flex items-center rounded-md bg-purple-500/10 px-2 py-0.5 text-xs font-medium text-purple-600 dark:text-purple-400">
            OpenClaw
          </span>
        );
      case 'hermes':
        return (
          <span className="inline-flex items-center rounded-md bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-600 dark:text-sky-400">
            Hermes
          </span>
        );
      case 'memos':
        return (
          <span className="inline-flex items-center rounded-md bg-indigo-500/10 px-2 py-0.5 text-xs font-medium text-indigo-600 dark:text-indigo-400">
            MemOS Graph
          </span>
        );
      case 'chatgpt_export':
        return (
          <span className="inline-flex items-center rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            ChatGPT Export
          </span>
        );
      case 'claude_project':
        return (
          <span className="inline-flex items-center rounded-md bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400">
            Claude Project
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {source}
          </span>
        );
    }
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (customInput.trim()) {
      onCustomScan(customInput.trim());
    }
  };

  return (
    <div className="flex flex-col rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-border/60">
        <div className="flex items-center gap-2">
          <FolderSearch className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-foreground">
            本地竞品记忆资产探测器
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">
          发现 {candidates.length} 处资产
        </span>
      </div>

      <form onSubmit={handleCustomSubmit} className="mt-4 flex gap-2">
        <label htmlFor="custom-scan-path" className="sr-only">
          自定义扫描目录或文件路径
        </label>
        <input
          id="custom-scan-path"
          type="text"
          value={customInput}
          onChange={(e) => setCustomInput(e.target.value)}
          placeholder="输入自定义路径扫描（例如 ~/.openclaw 或 ~/export.json）..."
          className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <button
          type="submit"
          disabled={isScanning || !customInput.trim()}
          className="rounded-lg bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
        >
          定向扫描
        </button>
      </form>

      <div className="mt-4 space-y-2.5 max-h-60 overflow-y-auto pr-1">
        {candidates.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 text-center text-xs text-muted-foreground">
            <Sparkles className="h-6 w-6 text-muted-foreground/60 mb-1" aria-hidden="true" />
            <p>未在默认目录发现竞品文件，可通过上方输入路径自定义探测。</p>
          </div>
        ) : (
          candidates.map((cand) => {
            const isSelected = selectedPath === cand.artifact_path;
            return (
              <div
                key={cand.artifact_path}
                className={`flex flex-col gap-1.5 rounded-lg border p-3 transition-colors ${
                  isSelected
                    ? 'border-primary bg-primary/5'
                    : 'border-border/60 bg-muted/20 hover:border-border hover:bg-muted/40'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span className="truncate text-xs font-medium font-mono text-foreground" title={cand.artifact_path}>
                      {cand.artifact_path}
                    </span>
                  </div>
                  {getSourceBadge(cand.source_type)}
                </div>

                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="truncate pr-2">{cand.summary}</span>
                  <span className="shrink-0 font-medium text-foreground">
                    约 {cand.estimated_entries} 条记忆
                  </span>
                </div>

                <div className="mt-1 flex justify-end">
                  <button
                    type="button"
                    onClick={() => onSelectCandidate(cand)}
                    className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 focus:outline-none focus:ring-2 focus:ring-primary rounded px-1.5 py-0.5"
                    aria-label={`选择导入 ${cand.artifact_path}`}
                  >
                    {isSelected ? (
                      <>
                        <CheckCircle2 className="h-3 w-3 text-emerald-500" aria-hidden="true" />
                        已选择
                      </>
                    ) : (
                      <>
                        选择导入
                        <ArrowRight className="h-3 w-3" aria-hidden="true" />
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
