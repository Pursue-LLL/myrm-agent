import React from 'react';
import { MeshAuditLog } from './types';

export interface AuditLogsViewProps {
  logs: MeshAuditLog[];
}

export const AuditLogsView: React.FC<AuditLogsViewProps> = ({ logs }) => {
  return (
    <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
      {logs.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No mesh audit events recorded yet.</p>
      ) : (
        logs.map((log, idx) => (
          <div
            key={`${log.timestamp}-${idx}`}
            className="p-2.5 rounded-lg border border-border/70 bg-muted/15 text-xs space-y-1"
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-semibold">
                {log.eventType}
              </span>
              <span className="text-[10px] text-muted-foreground font-mono">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <div className="text-[11px] text-foreground">
              Node: <span className="font-semibold">{log.node}</span> | Project:{' '}
              <span className="font-mono">{log.project}</span>
            </div>
            <p className="text-[11px] text-muted-foreground">{log.detail}</p>
          </div>
        ))
      )}
    </div>
  );
};
