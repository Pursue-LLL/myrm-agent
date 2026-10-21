'use client';

/**
 * [INPUT]
 * - ./types::ProcessLineageNode (POS: 进程树节点定义)
 * - lucide-react::GitCommit, ArrowRight, AlertTriangle, Terminal, Folder (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - ProcessLineageView: 进程父子派生调用链路追踪视图组件
 *
 * [POS]
 * src/components/features/system-monitor/ProcessLineageView.tsx — 启动链路与进程树逆向溯源卡片。
 */

import React from 'react';
import { GitCommit, ArrowRight, AlertTriangle, Terminal, Folder } from 'lucide-react';
import type { ProcessLineageNode } from './types';

interface ProcessLineageViewProps {
  lineage: ProcessLineageNode[];
  className?: string;
}

export const ProcessLineageView: React.FC<ProcessLineageViewProps> = ({
  lineage,
  className = '',
}) => {
  if (!lineage || lineage.length === 0) {
    return (
      <div className={`p-4 text-xs text-muted-foreground text-center bg-muted/20 rounded-md ${className}`}>
        暂无可用进程派生调用链路数据
      </div>
    );
  }

  return (
    <div
      data-testid="process-lineage-view"
      className={`space-y-3 rounded-lg border border-border/60 bg-muted/10 p-3.5 text-xs ${className}`}
    >
      <div className="flex items-center gap-1.5 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
        <GitCommit className="w-3.5 h-3.5 text-primary" />
        <span>进程启动父子链路溯源 (Launch Lineage)</span>
      </div>

      <div className="flex flex-col gap-2">
        {lineage.map((node, index) => {
          const isTarget = index === lineage.length - 1;
          const cmdString = node.cmdline.length > 0 ? node.cmdline.join(' ') : node.name;

          return (
            <div key={`${node.pid}-${index}`} className="flex flex-col gap-1.5">
              <div
                className={`flex items-center justify-between p-2 rounded-md border transition-colors ${
                  node.is_high_resource
                    ? 'border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200'
                    : isTarget
                      ? 'border-primary/40 bg-primary/5 text-foreground font-medium'
                      : 'border-border/40 bg-muted/20 text-muted-foreground'
                }`}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-foreground">
                    PID {node.pid}
                  </span>
                  <span className="font-semibold truncate">{node.name}</span>
                  {node.username && (
                    <span className="text-[10px] text-muted-foreground">({node.username})</span>
                  )}
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  {node.is_high_resource && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded">
                      <AlertTriangle className="w-2.5 h-2.5" />
                      高资源占用
                    </span>
                  )}
                  {isTarget && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-primary/20 text-primary font-medium rounded">
                      目标进程
                    </span>
                  )}
                </div>
              </div>

              {/* 命令与目录详情 */}
              <div className="px-2.5 text-[10px] text-muted-foreground font-mono space-y-0.5">
                <div className="flex items-start gap-1 truncate" title={cmdString}>
                  <Terminal className="w-2.5 h-2.5 mt-0.5 shrink-0 opacity-70" />
                  <span className="truncate">{cmdString}</span>
                </div>
                {node.cwd && (
                  <div className="flex items-center gap-1 truncate" title={node.cwd}>
                    <Folder className="w-2.5 h-2.5 shrink-0 opacity-70" />
                    <span className="truncate">{node.cwd}</span>
                  </div>
                )}
              </div>

              {index < lineage.length - 1 && (
                <div className="flex justify-center my-0.5">
                  <ArrowRight className="w-3 h-3 text-muted-foreground/40 rotate-90" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
