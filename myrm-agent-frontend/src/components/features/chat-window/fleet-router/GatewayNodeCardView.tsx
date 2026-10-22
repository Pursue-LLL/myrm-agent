import React from 'react';
import {
  FleetProfile,
  GatewayNode,
  GatewayPlatformType,
  GatewayStatusType,
} from './types';

export interface GatewayNodeCardViewProps {
  gateway: GatewayNode;
  profiles: FleetProfile[];
  activeProfileId: string | null;
  bufferedCount: number;
  onSelectProfile: (profileId: string) => void;
  onSimulateCommand: (gatewayId: string, profileId: string) => void;
  onFlushGateway: (gatewayId: string) => void;
}

export const GatewayNodeCardView: React.FC<GatewayNodeCardViewProps> = ({
  gateway,
  profiles,
  activeProfileId,
  bufferedCount,
  onSelectProfile,
  onSimulateCommand,
  onFlushGateway,
}) => {
  const isOffline = gateway.status === 'offline';
  const isDegraded = gateway.status === 'degraded';

  const getPlatformIcon = (platform: GatewayPlatformType) => {
    switch (platform) {
      case 'darwin':
        return '🍎 macOS';
      case 'linux':
        return '🐧 Linux';
      case 'vps':
        return '🌐 VPS';
      case 'cloud':
        return '☁️ Cloud';
    }
  };

  const getStatusBadge = (status: GatewayStatusType) => {
    switch (status) {
      case 'online':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-500 border border-emerald-500/20">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            ONLINE
          </span>
        );
      case 'degraded':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-500 border border-amber-500/20">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            DEGRADED
          </span>
        );
      case 'offline':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-0.5 text-[11px] font-semibold text-rose-500 border border-rose-500/20">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
            OFFLINE
          </span>
        );
    }
  };

  return (
    <div
      className={`flex flex-col rounded-xl border p-4 shadow-xs transition-all space-y-3.5 ${
        isOffline
          ? 'border-amber-500/40 bg-amber-500/5'
          : isDegraded
            ? 'border-amber-500/30 bg-card'
            : 'border-border/60 bg-card hover:border-primary/40'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground tracking-tight">
              {gateway.label}
            </h3>
            <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              {getPlatformIcon(gateway.platform)}
            </span>
          </div>
          <span className="text-xs font-mono text-muted-foreground">
            {gateway.protocol}://{gateway.host}:{gateway.port}
          </span>
        </div>
        <div className="flex flex-col items-end gap-1">
          {getStatusBadge(gateway.status)}
          {!isOffline && (
            <span className="text-[10px] font-mono text-muted-foreground">
              {gateway.latency_ms.toFixed(1)} ms
            </span>
          )}
        </div>
      </div>

      {/* Telemetry Resource Bars */}
      {!isOffline ? (
        <div className="grid grid-cols-2 gap-2.5 rounded-lg bg-muted/30 p-2.5 border border-border/30 text-xs">
          <div>
            <div className="flex justify-between text-[10px] text-muted-foreground font-mono mb-1">
              <span>CPU</span>
              <span>{gateway.telemetry.cpu_pct.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 transition-all duration-300"
                style={{ width: `${Math.min(100, gateway.telemetry.cpu_pct)}%` }}
              />
            </div>
          </div>
          <div>
            <div className="flex justify-between text-[10px] text-muted-foreground font-mono mb-1">
              <span>Memory</span>
              <span>{gateway.telemetry.mem_pct.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${Math.min(100, gateway.telemetry.mem_pct)}%` }}
              />
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-amber-500/10 p-2.5 border border-amber-500/20 text-xs space-y-1.5">
          <div className="flex items-center justify-between text-amber-500 font-medium">
            <span>⚠️ Gateway Unreachable</span>
            <span>Buffered: {bufferedCount} cmds</span>
          </div>
          <p className="text-[11px] text-muted-foreground leading-snug">
            All dispatched commands and tasks are transparently buffered in local FIFO queue and will auto-flush upon reconnection.
          </p>
        </div>
      )}

      {/* Profile Rail on this gateway */}
      <div className="space-y-2">
        <span className="text-xs font-semibold text-muted-foreground block">
          Agent Profiles ({profiles.length})
        </span>
        {profiles.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">No registered profiles on this gateway.</p>
        ) : (
          <div className="grid grid-cols-1 gap-1.5">
            {profiles.map((p) => {
              const isActive = activeProfileId === p.profile_id;
              return (
                <div
                  key={p.profile_id}
                  className={`flex items-center justify-between rounded-lg p-2 transition-all border ${
                    isActive
                      ? 'border-primary/60 bg-primary/10 shadow-xs'
                      : 'border-border/40 bg-muted/20 hover:bg-muted/40'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelectProfile(p.profile_id)}
                    className="flex items-center gap-2 text-left flex-1 min-w-0 mr-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="text-base">{p.avatar}</span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold text-foreground truncate">
                          {p.name}
                        </span>
                        {isActive && (
                          <span className="rounded bg-primary/20 text-primary px-1 py-0.2 text-[9px] font-mono font-bold uppercase">
                            Active
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-foreground truncate block font-mono">
                        {p.role}
                      </span>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => onSimulateCommand(gateway.gateway_id, p.profile_id)}
                    className="rounded bg-muted px-2 py-1 text-[10px] font-medium text-foreground hover:bg-primary hover:text-primary-foreground transition-colors shrink-0"
                  >
                    {isOffline ? 'Buffer Cmd' : 'Send Task'}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer Actions */}
      {isOffline && bufferedCount > 0 && (
        <div className="pt-2 border-t border-border/40 flex justify-end">
          <button
            type="button"
            onClick={() => onFlushGateway(gateway.gateway_id)}
            className="rounded-md bg-amber-500/20 text-amber-500 border border-amber-500/30 px-2.5 py-1 text-xs font-semibold hover:bg-amber-500 hover:text-white transition-colors shadow-xs"
          >
            ⚡ Reconnect & Flush ({bufferedCount})
          </button>
        </div>
      )}
    </div>
  );
};
