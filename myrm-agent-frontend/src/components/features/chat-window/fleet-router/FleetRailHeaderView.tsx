import React from 'react';

export interface FleetRailHeaderViewProps {
  totalGateways: number;
  onlineGateways: number;
  bufferedCount: number;
  isRefreshing: boolean;
  onRefresh: () => void;
  onOpenBufferModal: () => void;
  onOpenRelayModal: () => void;
}

export const FleetRailHeaderView: React.FC<FleetRailHeaderViewProps> = ({
  totalGateways,
  onlineGateways,
  bufferedCount,
  isRefreshing,
  onRefresh,
  onOpenBufferModal,
  onOpenRelayModal,
}) => {
  return (
    <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 font-bold border border-emerald-500/20 shadow-xs">
          🛰️
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              Fleet-Wide Profile Rail
            </h2>
            <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-500 border border-emerald-500/20">
              Distributed Fleet
            </span>
            <span className="inline-flex items-center rounded-full bg-indigo-500/10 px-2 py-0.5 text-xs font-medium text-indigo-500 border border-indigo-500/20">
              Host Context Aware
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Aggregate Mac, Linux, VPS and Cloud gateways into a single unified navigation rail with auto-healing and artifact relay.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 self-stretch sm:self-auto justify-between sm:justify-end">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium mr-1">
          <span className="rounded bg-muted px-2 py-1">
            Gateways: <strong className="text-foreground">{onlineGateways}/{totalGateways}</strong>
          </span>
          {bufferedCount > 0 && (
            <button
              type="button"
              onClick={onOpenBufferModal}
              className="rounded bg-amber-500/10 text-amber-500 px-2 py-1 border border-amber-500/20 hover:bg-amber-500/20 transition-colors font-semibold"
            >
              Offline Buffer: <strong>{bufferedCount}</strong>
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={onOpenRelayModal}
          className="rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2.5 py-1 text-xs font-medium text-indigo-500 hover:bg-indigo-500/20 transition-colors"
        >
          📦 Relay Artifact
        </button>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground hover:bg-muted/80 transition-colors shadow-xs disabled:opacity-50"
        >
          {isRefreshing ? 'Pinging...' : '↻ Refresh'}
        </button>
      </div>
    </header>
  );
};
