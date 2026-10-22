import React from 'react';
import { ExternalBundleProfileSpec } from './types';

export interface BundleCatalogViewProps {
  bundles: ExternalBundleProfileSpec[];
  probingBundleId: string | null;
  onProbeBundle: (bundleId: string) => Promise<void>;
  onSelectForDispatch: (bundleId: string) => void;
}

export const BundleCatalogView: React.FC<BundleCatalogViewProps> = ({
  bundles,
  probingBundleId,
  onProbeBundle,
  onSelectForDispatch,
}) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Registered Subagent Bundles</h3>
          <p className="text-xs text-muted-foreground">
            Packaged CLI execution adapters with sandboxed scope policies and environment containment.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {bundles.map((bundle) => {
          const isProbing = probingBundleId === bundle.bundle_id;
          return (
            <div
              key={bundle.bundle_id}
              className="flex flex-col justify-between rounded-lg border border-border/50 bg-card/60 p-3.5 shadow-sm transition-all hover:border-border hover:bg-card"
            >
              <div className="space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h4 className="text-sm font-bold text-foreground tracking-tight">
                      {bundle.display_name}
                    </h4>
                    <p className="text-[11px] font-mono text-muted-foreground">
                      binary: <span className="font-semibold text-foreground">{bundle.binary_name}</span>
                    </p>
                  </div>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium border ${
                      bundle.is_installed
                        ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                        : 'bg-amber-500/10 text-amber-500 border-amber-500/20'
                    }`}
                  >
                    {bundle.is_installed ? `v${bundle.version}` : 'Not Installed'}
                  </span>
                </div>

                <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                  {bundle.description}
                </p>

                <div className="flex flex-wrap gap-1.5 pt-1">
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-mono text-primary">
                    concurrency: ≤{bundle.max_concurrency}
                  </span>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                    mode: {bundle.execution_mode}
                  </span>
                </div>

                <div className="space-y-1">
                  <span className="text-[10px] uppercase font-semibold text-muted-foreground tracking-wider">
                    Capabilities:
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {bundle.capabilities.map((cap) => (
                      <span
                        key={cap}
                        className="rounded-full bg-secondary/80 px-2 py-0.5 text-[10px] text-secondary-foreground"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-4 flex items-center gap-2 pt-2 border-t border-border/30">
                <button
                  type="button"
                  onClick={() => onProbeBundle(bundle.bundle_id)}
                  disabled={isProbing}
                  className="flex-1 rounded-md border border-border/60 bg-muted/40 px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                >
                  {isProbing ? 'Probing...' : 'Probe Host'}
                </button>
                <button
                  type="button"
                  onClick={() => onSelectForDispatch(bundle.bundle_id)}
                  className="flex-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
                >
                  Use for Dispatch
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
