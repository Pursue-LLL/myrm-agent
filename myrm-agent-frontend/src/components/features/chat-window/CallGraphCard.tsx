'use client';

/**
 * [INPUT]
 * - target: 目标函数或类名
 * - callers: 调用方列表（包含文件路径、行号、列号、实参个数、调用参数）
 * - reachingTests: 反向拓扑触达的关联测试列表（包含测试名称、文件路径、距离深度）
 * - onRunTests: 可选回调，点击一键执行受影响测试
 *
 * [OUTPUT]
 * - CallGraphCard: 优雅直观的代码调用图与改动爆炸半径卡片组件
 *
 * [POS]
 * 在聊天会话中展示 Agent 使用 repo-call-graph 技能解析出的调用拓扑和受影响测试清单。
 */

import React, { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { GitCommit, ShieldCheck, ChevronDown, ChevronRight, FileCode2, TestTube2, ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';

export interface CallSiteItem {
  caller: string;
  callee: string;
  file_path: string;
  line: number;
  col: number;
  arg_count?: number;
  kwarg_names?: string[];
}

export interface ReachingTestItem {
  test_symbol: string;
  file_path: string;
  line: number;
  distance: number;
}

export interface CallGraphCardProps {
  target: string;
  callers?: CallSiteItem[];
  reachingTests?: ReachingTestItem[];
  className?: string;
  onRunTests?: (testFiles: string[]) => void;
}

export const CallGraphCard: React.FC<CallGraphCardProps> = memo(({
  target,
  callers = [],
  reachingTests = [],
  className,
  onRunTests,
}) => {
  const t = useTranslations('chat.callGraph');
  const [showCallers, setShowCallers] = useState(true);
  const [showTests, setShowTests] = useState(true);

  const testFilePaths = Array.from(new Set(reachingTests.map((tItem) => tItem.file_path)));

  return (
    <div
      className={cn(
        'w-full max-w-2xl rounded-xl border border-border/60 bg-card p-4 text-card-foreground shadow-sm transition-all',
        className
      )}
    >
      {/* 头部：目标符号与统计摘要 */}
      <div className="flex items-center justify-between border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <GitCommit className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs font-medium text-muted-foreground">{t('title')}</div>
            <div className="font-mono text-sm font-semibold text-foreground">{target}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
            {callers.length} {t('callers')}
          </span>
          <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
            {reachingTests.length} {t('reachingTests')}
          </span>
        </div>
      </div>

      {/* 调用方列表折叠区块 */}
      <div className="mt-3">
        <button
          type="button"
          onClick={() => setShowCallers(!showCallers)}
          className="flex w-full items-center justify-between py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          <span className="flex items-center gap-1.5">
            <FileCode2 className="h-3.5 w-3.5" />
            {t('physicalCallChain')} ({callers.length})
          </span>
          {showCallers ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>

        {showCallers && (
          <div className="mt-2 space-y-1.5 pl-2">
            {callers.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">{t('noCallers')}</div>
            ) : (
              callers.map((c, idx) => (
                <div
                  key={`${c.file_path}-${c.line}-${idx}`}
                  className="flex flex-col rounded-md bg-muted/40 p-2 text-xs transition-colors hover:bg-muted/70"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-medium text-foreground">{c.caller}</span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {c.file_path}:{c.line}
                    </span>
                  </div>
                  {c.kwarg_names && c.kwarg_names.length > 0 && (
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {t('params')}: {c.kwarg_names.join(', ')}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 关联测试与爆炸半径区块 */}
      <div className="mt-4 border-t border-border/40 pt-3">
        <button
          type="button"
          onClick={() => setShowTests(!showTests)}
          className="flex w-full items-center justify-between py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          <span className="flex items-center gap-1.5">
            <TestTube2 className="h-3.5 w-3.5 text-primary" />
            {t('testImpact')} ({reachingTests.length})
          </span>
          {showTests ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>

        {showTests && (
          <div className="mt-2 space-y-1.5 pl-2">
            {reachingTests.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">{t('noTests')}</div>
            ) : (
              reachingTests.map((tItem, idx) => (
                <div
                  key={`${tItem.file_path}-${tItem.test_symbol}-${idx}`}
                  className="flex items-center justify-between rounded-md bg-primary/5 p-2 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-3.5 w-3.5 text-primary shrink-0" />
                    <div>
                      <div className="font-mono font-medium text-foreground">{tItem.test_symbol}</div>
                      <div className="text-[11px] text-muted-foreground">{tItem.file_path}:{tItem.line}</div>
                    </div>
                  </div>
                  <span className="rounded bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground border border-border/40">
                    {t('depth')} {tItem.distance} {t('level')}
                  </span>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 底部操作区：一键执行受影响测试 */}
      {onRunTests && testFilePaths.length > 0 && (
        <div className="mt-4 flex items-center justify-end border-t border-border/40 pt-3">
          <Button
            size="sm"
            variant="outline"
            onClick={() => onRunTests(testFilePaths)}
            className="h-8 gap-1.5 text-xs"
          >
            <ArrowUpRight className="h-3.5 w-3.5" />
            {t('runAffectedTests', { count: testFilePaths.length })}
          </Button>
        </div>
      )}
    </div>
  );
});

CallGraphCard.displayName = 'CallGraphCard';
