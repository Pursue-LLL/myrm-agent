import React from 'react';

export interface ForgeHeaderViewProps {
  activeTab: 'agent' | 'team' | 'catalog' | 'pipeline';
  onTabChange: (tab: 'agent' | 'team' | 'catalog' | 'pipeline') => void;
  totalAgents: number;
  isProcessing: boolean;
  onRefreshCatalog?: () => void;
}

export const ForgeHeaderView: React.FC<ForgeHeaderViewProps> = ({
  activeTab,
  onTabChange,
  totalAgents,
  isProcessing,
  onRefreshCatalog,
}) => {
  return (
    <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-500 font-bold border border-indigo-500/20 shadow-sm">
          ⚙️
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              Bot Forge & Team Studio
            </h2>
            <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-500 border border-emerald-500/20">
              Safety Envelope Active
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Deterministic creation pipeline with zero-model readiness dry run & atomic transactional rollback.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 self-stretch sm:self-auto justify-between sm:justify-end">
        <nav aria-label="Studio View Tabs" className="flex items-center rounded-lg bg-muted/60 p-1 border border-border/30">
          <button
            type="button"
            onClick={() => onTabChange('agent')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTab === 'agent'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Agent Forge
          </button>
          <button
            type="button"
            onClick={() => onTabChange('team')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTab === 'team'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Team Squad
          </button>
          <button
            type="button"
            onClick={() => onTabChange('catalog')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTab === 'catalog'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Catalog ({totalAgents})
          </button>
          <button
            type="button"
            onClick={() => onTabChange('pipeline')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTab === 'pipeline'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Pipeline
          </button>
        </nav>

        {onRefreshCatalog && (
          <button
            type="button"
            disabled={isProcessing}
            onClick={onRefreshCatalog}
            title="Refresh active catalog"
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border/40 text-muted-foreground hover:text-foreground hover:bg-muted/50 disabled:opacity-50"
          >
            🔄
          </button>
        )}
      </div>
    </header>
  );
};
