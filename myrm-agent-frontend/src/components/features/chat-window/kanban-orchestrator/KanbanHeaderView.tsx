import React from 'react';

export interface KanbanHeaderViewProps {
  title: string;
  totalCards: number;
  doneCards: number;
  blockedCards: number;
  isProcessing: boolean;
  onOpenDecompose: () => void;
  onOpenAddCard: () => void;
  onRefresh?: () => void;
}

export const KanbanHeaderView: React.FC<KanbanHeaderViewProps> = ({
  title,
  totalCards,
  doneCards,
  blockedCards,
  isProcessing,
  onOpenDecompose,
  onOpenAddCard,
  onRefresh,
}) => {
  return (
    <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-500 font-bold border border-indigo-500/20 shadow-xs">
          📋
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              {title}
            </h2>
            <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-500 border border-emerald-500/20">
              DAG Auto-Unblock Active
            </span>
            <span className="inline-flex items-center rounded-full bg-sky-500/10 px-2 py-0.5 text-xs font-medium text-sky-500 border border-sky-500/20">
              Card Sandbox Isolated
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Persistent task board orchestrating specialist agents with DAG prerequisite calculation and atomic artifact mounting.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 self-stretch sm:self-auto justify-between sm:justify-end">
        <div className="flex items-center gap-2 text-xs text-muted-foreground font-medium mr-1">
          <span className="rounded bg-muted px-2 py-1">
            Total: <strong className="text-foreground">{totalCards}</strong>
          </span>
          <span className="rounded bg-emerald-500/10 text-emerald-500 px-2 py-1 border border-emerald-500/20">
            Done: <strong>{doneCards}</strong>
          </span>
          {blockedCards > 0 && (
            <span className="rounded bg-amber-500/10 text-amber-500 px-2 py-1 border border-amber-500/20">
              Blocked: <strong>{blockedCards}</strong>
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={onOpenDecompose}
          disabled={isProcessing}
          className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-1 text-xs font-medium text-indigo-500 hover:bg-indigo-500/20 transition-colors disabled:opacity-50"
        >
          ⚡ Auto Decompose
        </button>

        <button
          type="button"
          onClick={onOpenAddCard}
          disabled={isProcessing}
          className="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs disabled:opacity-50"
        >
          + Add Card
        </button>

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isProcessing}
            aria-label="Refresh Board State"
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border/40 bg-background text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
            title="Refresh Board State"
          >
            <span className={isProcessing ? 'animate-spin' : ''}>🔄</span>
          </button>
        )}
      </div>
    </header>
  );
};
