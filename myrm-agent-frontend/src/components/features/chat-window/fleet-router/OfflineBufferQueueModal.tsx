import React from 'react';
import { OfflineBufferedCommand } from './types';

export interface OfflineBufferQueueModalProps {
  isOpen: boolean;
  bufferedMap: Record<string, OfflineBufferedCommand[]>;
  onClose: () => void;
  onFlush: (gatewayId: string) => void;
}

export const OfflineBufferQueueModal: React.FC<OfflineBufferQueueModalProps> = ({
  isOpen,
  bufferedMap,
  onClose,
  onFlush,
}) => {
  if (!isOpen) {
    return null;
  }

  const allBufferedEntries = Object.entries(bufferedMap);
  const totalCount = allBufferedEntries.reduce((acc, [, list]) => acc + list.length, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 backdrop-blur-xs p-4">
      <dialog
        open
        className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl space-y-4 max-h-[85vh] overflow-y-auto m-0"
        aria-label="Offline Command Buffer Modal"
      >
        <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="text-amber-500 text-base">⏳</span>
            <h3 className="text-sm font-bold text-foreground">
              Offline Command Buffer ({totalCount})
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          Commands directed towards offline gateways are safely retained in a FIFO queue. When the gateway comes back online, they are flushed in deterministic sequence.
        </p>

        {totalCount === 0 ? (
          <div className="flex items-center justify-center h-32 rounded-lg border border-dashed border-border/60 text-xs text-muted-foreground italic">
            Buffer is empty. All gateways operating normally.
          </div>
        ) : (
          <div className="space-y-4">
            {allBufferedEntries.map(([gatewayId, list]) => {
              if (list.length === 0) {
                return null;
              }
              return (
                <div
                  key={gatewayId}
                  className="rounded-lg border border-border/60 bg-muted/20 p-3 space-y-2.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-semibold text-foreground">
                      Gateway: {gatewayId}
                    </span>
                    <button
                      type="button"
                      onClick={() => onFlush(gatewayId)}
                      className="rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 px-2 py-0.5 text-xs font-medium hover:bg-amber-500 hover:text-white transition-colors"
                    >
                      Flush Queue ({list.length})
                    </button>
                  </div>

                  <div className="space-y-1.5">
                    {list.map((cmd) => (
                      <div
                        key={cmd.command_id}
                        className="rounded-md border border-border/40 bg-background/80 p-2 text-xs space-y-1 font-mono"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-primary font-bold">{cmd.command_type}</span>
                          <span className="text-[10px] text-muted-foreground">{cmd.command_id}</span>
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Target Profile: <strong className="text-foreground">{cmd.profile_id}</strong>
                        </div>
                        <div className="text-[10px] text-foreground bg-muted/40 p-1.5 rounded overflow-x-auto truncate">
                          {JSON.stringify(cmd.payload)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex justify-end pt-2 border-t border-border/30">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
          >
            Close
          </button>
        </div>
      </dialog>
    </div>
  );
};
