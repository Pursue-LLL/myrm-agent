'use client';

/**
 * [INPUT]
 * - computeFileDiff from @/services/workbench
 * - useWorkbenchStore from @/store/useWorkbenchStore
 * - useTranslations from next-intl (namespace: 'workbench.diff')
 *
 * [OUTPUT]
 * - WorkbenchDiffViewer: Side-by-side & inline code diff viewer with stats and hunk badges
 *
 * [POS]
 * Auxiliary Workbench Diff tab component.
 * Single file < 300 lines. Zero `any` types. Zero native emoji.
 */

import React, { useState, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  GitCommit,
  Columns,
  AlignJustify,
  FileDiff,
  Check,
  Undo2,
  Plus,
  Minus,
} from 'lucide-react';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import type { FileDiffResponse } from '@/services/workbench';

export function WorkbenchDiffViewer() {
  const t = useTranslations('workbench.diff');
  const [viewMode, setViewMode] = useState<'inline' | 'split'>('inline');
  const [isCopied, setIsCopied] = useState<boolean>(false);

  const activeDiff = useWorkbenchStore((s) => s.activeDiff);
  const setActiveDiff = useWorkbenchStore((s) => s.setActiveDiff);

  // Mock demo diff if no active diff loaded
  const displayDiff: FileDiffResponse = useMemo(() => {
    if (activeDiff) {
      return activeDiff;
    }
    return {
      file_path: 'src/components/features/agent/runtime.ts',
      unified_diff: [
        '--- a/src/components/features/agent/runtime.ts',
        '+++ b/src/components/features/agent/runtime.ts',
        '@@ -12,5 +12,7 @@ export class AgentRuntime {',
        '   private heartbeatInterval: number = 3000;',
        '-  private isIsolated: boolean = false;',
        '+  private isIsolated: boolean = true;',
        '+  private sandboxVolumeId: string = "vol-prod-99";',
        '   public start(): void {',
      ].join('\n'),
      additions: 2,
      deletions: 1,
      hunks: [
        {
          old_start: 12,
          old_lines: 5,
          new_start: 12,
          new_lines: 7,
          lines: [
            '   private heartbeatInterval: number = 3000;',
            '-  private isIsolated: boolean = false;',
            '+  private isIsolated: boolean = true;',
            '+  private sandboxVolumeId: string = "vol-prod-99";',
            '   public start(): void {',
          ],
        },
      ],
    };
  }, [activeDiff]);

  const diffLines = useMemo(() => {
    return displayDiff.unified_diff.split('\n');
  }, [displayDiff.unified_diff]);

  const handleCopyUnifiedDiff = () => {
    void navigator.clipboard.writeText(displayDiff.unified_diff);
    setIsCopied(true);
    window.setTimeout(() => setIsCopied(false), 1500);
  };

  const handleClearDiff = () => {
    setActiveDiff(null);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden text-foreground">
      {/* Diff Toolbar */}
      <div className="p-2 border-b border-border/60 flex items-center justify-between gap-2 bg-card/60 text-xs">
        <div className="flex items-center gap-2 truncate">
          <FileDiff className="w-4 h-4 text-primary shrink-0" />
          <span className="font-mono font-medium truncate">{displayDiff.file_path}</span>
          <div className="flex items-center gap-1 font-mono text-[11px] shrink-0">
            <span className="flex items-center text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded font-semibold">
              <Plus className="w-3 h-3 mr-0.5" />
              {displayDiff.additions}
            </span>
            <span className="flex items-center text-rose-600 dark:text-rose-400 bg-rose-500/10 px-1.5 py-0.2 rounded font-semibold">
              <Minus className="w-3 h-3 mr-0.5" />
              {displayDiff.deletions}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Mode Switcher */}
          <div className="inline-flex rounded-lg bg-muted/60 p-0.5 border border-border/40">
            <button
              type="button"
              onClick={() => setViewMode('inline')}
              className={`p-1 rounded transition-colors ${
                viewMode === 'inline'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              title={t('modeInline')}
            >
              <AlignJustify className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode('split')}
              className={`p-1 rounded transition-colors ${
                viewMode === 'split'
                  ? 'bg-background text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              title={t('modeSplit')}
            >
              <Columns className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            type="button"
            onClick={handleCopyUnifiedDiff}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-muted/60 hover:bg-muted text-[11px] font-mono transition-colors"
          >
            {isCopied ? <Check className="w-3 h-3 text-emerald-500" /> : <GitCommit className="w-3 h-3" />}
            <span>{isCopied ? t('copied') : t('copyDiff')}</span>
          </button>

          {activeDiff && (
            <button
              type="button"
              onClick={handleClearDiff}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title={t('resetDiff')}
            >
              <Undo2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Diff Content Canvas */}
      <div className="flex-1 overflow-auto font-mono text-xs p-2 bg-background/70">
        {viewMode === 'inline' ? (
          <div className="flex flex-col">
            {diffLines.map((line, idx) => {
              const isHunkHeader = line.startsWith('@@');
              const isAdd = line.startsWith('+') && !line.startsWith('+++');
              const isDel = line.startsWith('-') && !line.startsWith('---');

              return (
                <div
                  key={`inline-line-${idx}`}
                  className={`flex items-start px-2 py-0.5 leading-relaxed font-mono ${
                    isHunkHeader
                      ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 font-semibold my-1 rounded'
                      : isAdd
                      ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-l-2 border-emerald-500'
                      : isDel
                      ? 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-l-2 border-rose-500'
                      : 'text-foreground/80 hover:bg-muted/30'
                  }`}
                >
                  <span className="w-8 select-none text-[10px] text-muted-foreground/60 text-right pr-2 shrink-0">
                    {idx + 1}
                  </span>
                  <span className="whitespace-pre flex-1 select-text">{line}</span>
                </div>
              );
            })}
          </div>
        ) : (
          /* Split / Side-by-side Mode */
          <div className="grid grid-cols-2 gap-2 h-full">
            <div className="flex flex-col border-r border-border/40 pr-2">
              <span className="text-[10px] uppercase font-bold text-rose-500 mb-1 px-1">
                {t('originalHeader')}
              </span>
              {diffLines
                .filter((l) => !l.startsWith('+') || l.startsWith('+++'))
                .map((l, i) => (
                  <div
                    key={`split-old-${i}`}
                    className={`px-1.5 py-0.5 whitespace-pre ${
                      l.startsWith('-')
                        ? 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-l-2 border-rose-500'
                        : 'text-foreground/75'
                    }`}
                  >
                    {l}
                  </div>
                ))}
            </div>

            <div className="flex flex-col pl-2">
              <span className="text-[10px] uppercase font-bold text-emerald-500 mb-1 px-1">
                {t('modifiedHeader')}
              </span>
              {diffLines
                .filter((l) => !l.startsWith('-') || l.startsWith('---'))
                .map((l, i) => (
                  <div
                    key={`split-new-${i}`}
                    className={`px-1.5 py-0.5 whitespace-pre ${
                      l.startsWith('+')
                        ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-l-2 border-emerald-500'
                        : 'text-foreground/75'
                    }`}
                  >
                    {l}
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
