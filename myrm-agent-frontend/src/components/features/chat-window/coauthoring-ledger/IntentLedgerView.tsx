import React from 'react';
import { DeltaEntryItem } from './types';

export interface IntentLedgerViewProps {
  deltas: DeltaEntryItem[];
}

export const IntentLedgerView: React.FC<IntentLedgerViewProps> = ({ deltas }) => {
  return (
    <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
      {deltas.map((d) => (
        <div key={d.deltaId} className="p-2 rounded border border-border/70 bg-muted/10 text-xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] text-primary">{d.deltaId}</span>
            <span className="text-[10px] text-muted-foreground">{new Date(d.timestamp).toLocaleTimeString()}</span>
          </div>
          <div className="text-[11px] text-foreground">
            <span className="font-semibold">{d.authorId}</span> [{d.authorType}] applied{' '}
            <code className="text-primary">{d.operation}</code> on {d.blockId}
          </div>
          <p className="text-[10px] text-muted-foreground italic">Reason: {d.intentReason}</p>
        </div>
      ))}
    </div>
  );
};
