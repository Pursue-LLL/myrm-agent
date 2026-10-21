import React, { useState } from 'react';
import { GatewayNode, RelayedArtifact } from './types';

export interface CrossGatewayRelayModalProps {
  isOpen: boolean;
  gateways: GatewayNode[];
  isRelaying: boolean;
  onClose: () => void;
  onRelay: (
    sourceGateway: string,
    targetGateway: string,
    name: string,
    filePath: string,
    chunkData: string,
  ) => Promise<RelayedArtifact | null>;
}

export const CrossGatewayRelayModal: React.FC<CrossGatewayRelayModalProps> = ({
  isOpen,
  gateways,
  isRelaying,
  onClose,
  onRelay,
}) => {
  const [sourceGateway, setSourceGateway] = useState<string>(gateways[0]?.gateway_id || '');
  const [targetGateway, setTargetGateway] = useState<string>(gateways[1]?.gateway_id || gateways[0]?.gateway_id || '');
  const [name, setName] = useState<string>('benchmark_summary.json');
  const [filePath, setFilePath] = useState<string>('reports/eval.json');
  const [chunkData, setChunkData] = useState<string>('{"model": "qwen2.5-coder", "pass_rate": 0.942}');
  const [lastRelayed, setLastRelayed] = useState<RelayedArtifact | null>(null);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceGateway || !targetGateway || !name.trim() || isRelaying) {
      return;
    }
    const res = await onRelay(
      sourceGateway,
      targetGateway,
      name.trim(),
      filePath.trim(),
      chunkData.trim(),
    );
    if (res) {
      setLastRelayed(res);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 backdrop-blur-xs p-4">
      <dialog
        open
        className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto m-0"
        aria-label="Cross-Gateway Artifact Relay Modal"
      >
        <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="text-base">📦</span>
            <h3 className="text-sm font-bold text-foreground">
              Cross-Gateway Artifact Relay
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
          Transparently stream and relay output artifacts (code diffs, JSON reports, binaries) across distributed gateways with SHA-256 integrity verification.
        </p>

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="relay-source-gw" className="block text-xs font-semibold text-muted-foreground mb-1">
                Source Gateway
              </label>
              <select
                id="relay-source-gw"
                value={sourceGateway}
                onChange={(e) => setSourceGateway(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground"
              >
                {gateways.map((g) => (
                  <option key={g.gateway_id} value={g.gateway_id}>
                    {g.label} ({g.platform})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="relay-target-gw" className="block text-xs font-semibold text-muted-foreground mb-1">
                Target Gateway
              </label>
              <select
                id="relay-target-gw"
                value={targetGateway}
                onChange={(e) => setTargetGateway(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground"
              >
                {gateways.map((g) => (
                  <option key={g.gateway_id} value={g.gateway_id}>
                    {g.label} ({g.platform})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="relay-art-name" className="block text-xs font-semibold text-muted-foreground mb-1">
                Artifact Title
              </label>
              <input
                id="relay-art-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. results.json"
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground"
                required
              />
            </div>

            <div>
              <label htmlFor="relay-art-path" className="block text-xs font-semibold text-muted-foreground mb-1">
                Remote Path
              </label>
              <input
                id="relay-art-path"
                type="text"
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                placeholder="e.g. dist/bundle.js"
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground font-mono"
              />
            </div>
          </div>

          <div>
            <label htmlFor="relay-chunk-data" className="block text-xs font-semibold text-muted-foreground mb-1">
              Payload Content (Chunk Data)
            </label>
            <textarea
              id="relay-chunk-data"
              value={chunkData}
              onChange={(e) => setChunkData(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground font-mono focus:ring-1 focus:ring-primary"
              required
            />
          </div>

          {lastRelayed && (
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2.5 text-xs space-y-1 font-mono">
              <div className="flex items-center justify-between text-emerald-500 font-bold">
                <span>✓ Relayed Successfully</span>
                <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 text-[10px]">Verified SHA-256</span>
              </div>
              <div className="text-[11px] text-muted-foreground truncate">
                Artifact ID: {lastRelayed.artifact_id}
              </div>
              <div className="text-[10px] text-foreground truncate">
                Hash: {lastRelayed.sha256}
              </div>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/30">
            <button
              type="button"
              onClick={onClose}
              disabled={isRelaying}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={isRelaying}
              className="rounded-md bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors shadow-xs disabled:opacity-50"
            >
              {isRelaying ? 'Relaying...' : 'Relay Artifact via Secure Tunnel'}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
};
