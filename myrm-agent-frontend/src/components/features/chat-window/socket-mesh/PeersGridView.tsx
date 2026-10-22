import React from 'react';
import { PeerInfo } from './types';

export interface PeersGridViewProps {
  peers: PeerInfo[];
  onPingPeer: (targetName: string) => void;
  isProcessing: boolean;
}

export const PeersGridView: React.FC<PeersGridViewProps> = ({
  peers,
  onPingPeer,
  isProcessing,
}) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {peers.map((peer) => {
        const isOnline = peer.status === 'online';
        return (
          <div
            key={peer.name}
            className="p-3 rounded-lg border border-border bg-card/60 flex flex-col justify-between text-xs space-y-2"
          >
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-foreground font-mono text-xs">{peer.name}</span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded font-mono font-semibold uppercase ${
                    isOnline
                      ? 'bg-emerald-500/10 text-emerald-600'
                      : peer.status === 'stale'
                      ? 'bg-amber-500/10 text-amber-600'
                      : 'bg-red-500/10 text-red-600'
                  }`}
                >
                  {peer.status}
                </span>
              </div>
              <p className="text-muted-foreground text-[11px] line-clamp-2">{peer.purpose}</p>
            </div>

            <div className="space-y-1 text-[11px] text-muted-foreground pt-1 border-t border-border/50">
              <div className="flex justify-between">
                <span>Model:</span>
                <span className="font-mono text-foreground">{peer.model}</span>
              </div>
              <div className="flex justify-between">
                <span>PID:</span>
                <span className="font-mono text-foreground">{peer.pid}</span>
              </div>
              <div className="flex justify-between">
                <span>Context:</span>
                <span className="font-mono text-foreground">{peer.contextUsedPct}%</span>
              </div>
              <div className="flex justify-between">
                <span>Queue:</span>
                <span className="font-mono text-foreground">{peer.queueDepth} in-flight</span>
              </div>
              <div className="truncate text-[10px] text-muted-foreground font-mono mt-1" title={peer.endpoint}>
                Socket: {peer.endpoint}
              </div>
            </div>

            <button
              type="button"
              disabled={isProcessing}
              onClick={() => onPingPeer(peer.name)}
              className="mt-2 w-full py-1 text-[11px] font-medium bg-muted text-muted-foreground rounded hover:bg-muted/80 transition-colors"
            >
              Ping Peer Health
            </button>
          </div>
        );
      })}
    </div>
  );
};
