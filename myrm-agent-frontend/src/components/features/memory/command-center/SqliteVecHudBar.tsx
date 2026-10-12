/**
 * [INPUT]
 * @/services/memory::SqliteVecStatsResponse
 * Lucide icons (Database, HardDrive, Cpu, FileCheck2, RefreshCw)
 *
 * [OUTPUT]
 * Component: SqliteVecHudBar
 *
 * [POS]
 * Operational HUD header for Item 130 SqliteVec Embedded Vector Store Studio.
 * Strictly typed, zero any, a11y compliant with visible focus rings. Single file < 200 lines.
 */

'use client';

import React from 'react';
import { Cpu, Database, FileCheck2, HardDrive, RefreshCw } from 'lucide-react';
import type { SqliteVecStatsResponse } from '@/services/memory';

interface SqliteVecHudBarProps {
  stats: SqliteVecStatsResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export const SqliteVecHudBar: React.FC<SqliteVecHudBarProps> = ({
  stats,
  isLoading,
  onRefresh,
}) => {
  const isNativeSIMD = stats?.engine_mode === 'native_vec0';
  const isHealthy = stats?.status === 'healthy';

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border/60 bg-muted/20 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-6">
        {/* Engine mode & health badge */}
        <div className="flex items-center gap-2">
          <Database
            className={`h-4 w-4 ${isHealthy ? 'text-emerald-500' : 'text-amber-500'} ${
              isLoading ? 'animate-pulse' : ''
            }`}
            aria-hidden="true"
          />
          <span className="font-medium text-foreground">SQLite-Vec 嵌入式向量引擎</span>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
              isNativeSIMD
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
            }`}
          >
            {isNativeSIMD ? 'Native SIMD (vec0)' : 'Process BLOB (Fallback)'}
          </span>
        </div>

        {/* Database file size */}
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <HardDrive className="h-4 w-4 text-primary/70" aria-hidden="true" />
          <span>文件体积:</span>
          <span className="font-semibold text-foreground">
            {stats ? formatBytes(stats.file_size_bytes) : '--'}
          </span>
        </div>

        {/* Collections count */}
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Cpu className="h-4 w-4 text-primary/70" aria-hidden="true" />
          <span>向量集合:</span>
          <span className="font-semibold text-foreground">
            {stats?.collection_count ?? 0}
          </span>
        </div>

        {/* Total vector documents */}
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <FileCheck2 className="h-4 w-4 text-primary/70" aria-hidden="true" />
          <span>存储文档数:</span>
          <span className="font-semibold text-foreground">
            {stats?.total_documents ?? 0}
          </span>
        </div>
      </div>

      {/* Refresh metrics button */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground shadow-sm transition hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 disabled:pointer-events-none disabled:opacity-50"
          aria-label="刷新向量引擎统计指标"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          <span>刷新指标</span>
        </button>
      </div>
    </div>
  );
};
