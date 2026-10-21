'use client';

/**
 * [INPUT]
 * - useWorkspaceLayoutMode from '@/hooks/ui/useWorkspaceLayoutMode'
 * - React children components
 *
 * [OUTPUT]
 * - PresetWorkspaceGrid: Adaptive container applying 4 preset workspace layout CSS topologies
 *
 * [POS]
 * Viewport container wrapper for Four Preset Workspace Layout Switcher.
 * Strict typing: Zero `any`. File length < 200 lines. Accessible grid structure.
 */

import React, { memo } from 'react';
import {
  useWorkspaceLayoutMode,
  type PresetLayoutMode,
} from '@/hooks/ui/useWorkspaceLayoutMode';
import {
  IconCpu,
  IconTerminal,
  IconUsers,
  IconSparkles,
} from '@/components/features/icons/PremiumIcons';

export interface PresetWorkspaceGridProps {
  children: React.ReactNode;
  overrideMode?: PresetLayoutMode;
}

export const PresetWorkspaceGrid = memo(function PresetWorkspaceGrid({
  children,
  overrideMode,
}: PresetWorkspaceGridProps) {
  const { layoutMode: activeHookMode } = useWorkspaceLayoutMode();
  const activeMode = overrideMode ?? activeHookMode;

  switch (activeMode) {
    case 'copilot':
      return (
        <div
          data-testid="workspace-grid-copilot"
          className="w-full h-full min-h-0 flex flex-col lg:flex-row gap-4 p-3 overflow-hidden bg-background"
        >
          {/* Left panel placeholder for code review & diff inspector */}
          <aside className="hidden lg:flex w-80 shrink-0 flex-col rounded-2xl border border-border/80 bg-card/60 p-4 backdrop-blur-sm">
            <div className="flex items-center gap-2 pb-3 border-b border-border/40 text-xs font-semibold text-primary">
              <IconTerminal className="w-4 h-4" />
              <span>Copilot Code Review &amp; Diff</span>
            </div>
            <div className="flex-1 flex flex-col items-center justify-center text-center p-4 text-xs text-muted-foreground">
              <span className="font-mono text-[11px] opacity-75">
                AST Tree &amp; Terminal Live View
              </span>
            </div>
          </aside>

          {/* Main conversational & agent interaction arena */}
          <main className="flex-1 min-w-0 h-full flex flex-col overflow-hidden">
            {children}
          </main>
        </div>
      );

    case 'multi_agent':
      return (
        <div
          data-testid="workspace-grid-multi-agent"
          className="w-full h-full min-h-0 flex flex-col gap-3 p-3 overflow-hidden bg-background"
        >
          {/* Top Multi-Agent cluster status roster banner */}
          <header className="w-full rounded-xl border border-primary/20 bg-primary/5 p-2.5 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 font-medium text-primary">
              <IconUsers className="w-4 h-4" />
              <span>Multi-Agent Cluster Topology Active</span>
            </div>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary">
              Parallel Mesh Ready
            </span>
          </header>

          {/* Grid layout for concurrent agent panels and conversation */}
          <main className="flex-1 min-h-0 w-full overflow-hidden flex flex-col">
            {children}
          </main>
        </div>
      );

    case 'remote_compute':
      return (
        <div
          data-testid="workspace-grid-remote-compute"
          className="w-full h-full min-h-0 flex flex-col lg:flex-row-reverse gap-4 p-3 overflow-hidden bg-background"
        >
          {/* Right compute telemetry metrics sidebar */}
          <aside className="hidden lg:flex w-72 shrink-0 flex-col rounded-2xl border border-border/80 bg-card/60 p-4 backdrop-blur-sm">
            <div className="flex items-center gap-2 pb-3 border-b border-border/40 text-xs font-semibold text-primary">
              <IconCpu className="w-4 h-4" />
              <span>Remote Sandbox Telemetry</span>
            </div>
            <div className="flex-1 flex flex-col items-center justify-center text-center p-4 text-xs text-muted-foreground">
              <span className="font-mono text-[11px] opacity-75">
                GPU / Volume Offload Healthy
              </span>
            </div>
          </aside>

          {/* Main workload interaction frame */}
          <main className="flex-1 min-w-0 h-full flex flex-col overflow-hidden">
            {children}
          </main>
        </div>
      );

    case 'easy_minimal':
    default:
      return (
        <div
          data-testid="workspace-grid-easy-minimal"
          className="w-full h-full min-h-0 flex flex-col items-center justify-center p-2 sm:p-4 overflow-hidden bg-background"
        >
          {/* Centered minimalist focus container */}
          <main className="w-full max-w-4xl h-full flex flex-col overflow-hidden">
            {children}
          </main>
        </div>
      );
  }
});
