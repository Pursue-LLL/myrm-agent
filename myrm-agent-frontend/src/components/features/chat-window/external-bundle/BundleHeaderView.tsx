import React from 'react';

export type ExternalBundleTab = 'catalog' | 'dispatch' | 'monitor';

export interface BundleHeaderViewProps {
  activeTab: ExternalBundleTab;
  onTabChange: (tab: ExternalBundleTab) => void;
  totalBundles: number;
  activeInstancesCount: number;
  isProcessing: boolean;
  onRefresh?: () => void;
}

export const BundleHeaderView: React.FC<BundleHeaderViewProps> = ({
  activeTab,
  onTabChange,
  totalBundles,
  activeInstancesCount,
  isProcessing,
  onRefresh,
}) => {
  return (
    <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-500/10 text-sky-500 font-bold border border-sky-500/20 shadow-sm">
          📦
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              External Agent Bundle Manager
            </h2>
            <span className="inline-flex items-center rounded-full bg-indigo-500/10 px-2 py-0.5 text-xs font-medium text-indigo-500 border border-indigo-500/20">
              Lock-Free Multiplexer
            </span>
            <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-500 border border-emerald-500/20">
              Sandbox Isolated
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Containerize heterogeneous external CLI agents (Claude Code, Codex, Gemini CLI) with parallel concurrency & boundary containment.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 self-stretch sm:self-auto justify-between sm:justify-end">
        <nav aria-label="Bundle View Tabs" className="flex items-center rounded-lg bg-muted/60 p-1 border border-border/30">
          <button
            type="button"
            onClick={() => onTabChange('catalog')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTab === 'catalog'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Bundles ({totalBundles})
          </button>
          <button
            type="button"
            onClick={() => onTabChange('dispatch')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTab === 'dispatch'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Parallel Dispatch
          </button>
          <button
            type="button"
            onClick={() => onTabChange('monitor')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTab === 'monitor'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Monitor {activeInstancesCount > 0 ? `(${activeInstancesCount} Active)` : ''}
          </button>
        </nav>

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isProcessing}
            aria-label="Refresh Bundles and Instances"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-border/40 bg-background text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
            title="Refresh Bundles & Telemetry"
          >
            <span className={isProcessing ? 'animate-spin' : ''}>🔄</span>
          </button>
        )}
      </div>
    </header>
  );
};
