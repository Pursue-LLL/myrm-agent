/**
 * HUD Telemetry Bar for Multi-Platform Memory Migration and Import Wizard.
 */

import React from 'react';
import {
  Boxes,
  Database,
  Layers,
  RefreshCw,
  Scan,
  ShieldCheck,
  SplitSquareVertical,
} from 'lucide-react';

interface MemoryMigrationHudBarProps {
  totalDetected: number;
  supportedPlatformsCount: number;
  totalAdmitted: number;
  totalSkippedDuplicates: number;
  totalChunksGenerated: number;
  isLoading: boolean;
  onRefresh: () => void;
  onScan: () => void;
}

export const MemoryMigrationHudBar: React.FC<MemoryMigrationHudBarProps> = ({
  totalDetected,
  supportedPlatformsCount,
  totalAdmitted,
  totalSkippedDuplicates,
  totalChunksGenerated,
  isLoading,
  onRefresh,
  onScan,
}) => {
  return (
    <header
      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border/60 bg-muted/30 p-4 backdrop-blur-sm"
      aria-label="记忆迁移引擎监控指示栏"
    >
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Boxes className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold tracking-tight text-foreground">
                全平台记忆迁移引擎
              </h2>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                零成本资产导入
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              支持 OpenClaw &middot; Hermes &middot; ChatGPT &middot; Claude &middot; MemOS &middot; Markdown
            </p>
          </div>
        </div>

        <div className="h-8 w-px bg-border/60 hidden md:block" aria-hidden="true" />

        <div className="grid grid-cols-2 gap-4 sm:flex sm:items-center sm:gap-6">
          <div className="flex flex-col">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Scan className="h-3.5 w-3.5 text-blue-500" aria-hidden="true" />
              本地探测资产
            </span>
            <span className="text-base font-bold text-foreground">
              {totalDetected}
              <span className="text-xs font-normal text-muted-foreground ml-1">处</span>
            </span>
          </div>

          <div className="flex flex-col">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Layers className="h-3.5 w-3.5 text-indigo-500" aria-hidden="true" />
              支持生态
            </span>
            <span className="text-base font-bold text-foreground">
              {supportedPlatformsCount}
              <span className="text-xs font-normal text-muted-foreground ml-1">类</span>
            </span>
          </div>

          <div className="flex flex-col">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Database className="h-3.5 w-3.5 text-emerald-500" aria-hidden="true" />
              已接纳记忆
            </span>
            <span className="text-base font-bold text-emerald-600 dark:text-emerald-400">
              {totalAdmitted}
              <span className="text-xs font-normal text-muted-foreground ml-1">条</span>
            </span>
          </div>

          <div className="flex flex-col">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <SplitSquareVertical className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
              滑动分块
            </span>
            <span className="text-base font-bold text-amber-600 dark:text-amber-400">
              {totalChunksGenerated}
              <span className="text-xs font-normal text-muted-foreground ml-1">
                (已滤重 {totalSkippedDuplicates})
              </span>
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onScan}
          disabled={isLoading}
          aria-label="一键扫描本地记忆资产"
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 disabled:opacity-50"
        >
          <Scan className={`h-3.5 w-3.5 ${isLoading ? 'animate-pulse' : ''}`} aria-hidden="true" />
          一键探测
        </button>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="刷新迁移状态与生态配置"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
          刷新
        </button>
      </div>
    </header>
  );
};
