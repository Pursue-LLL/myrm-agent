import React, { useState } from 'react';
import { BotProfile, PipelineExecutionState } from './types';

export interface CatalogAndRollbackViewProps {
  catalog: BotProfile[];
  latestState: PipelineExecutionState | null;
  isProcessing: boolean;
  onDeleteAgent: (name: string) => Promise<void>;
  onCloneAgent: (sourceName: string, targetName: string, newDisplayName?: string) => Promise<void>;
}

export const CatalogAndRollbackView: React.FC<CatalogAndRollbackViewProps> = ({
  catalog,
  latestState,
  isProcessing,
  onDeleteAgent,
  onCloneAgent,
}) => {
  const [cloningSource, setCloningSource] = useState<string | null>(null);
  const [cloneTargetName, setCloneTargetName] = useState<string>('');
  const [cloneDisplayName, setCloneDisplayName] = useState<string>('');

  const handleStartClone = (bot: BotProfile) => {
    setCloningSource(bot.name);
    setCloneTargetName(`${bot.name}-v2`);
    setCloneDisplayName(`${bot.display_name} v2`);
  };

  const handleConfirmClone = async () => {
    if (!cloningSource || !cloneTargetName.trim()) {
      return;
    }
    await onCloneAgent(cloningSource, cloneTargetName.trim(), cloneDisplayName.trim());
    setCloningSource(null);
  };

  return (
    <div className="space-y-4">
      {/* Pipeline & Rollback Telemetry Strip */}
      {latestState && (
        <section aria-labelledby="pipeline-telemetry-title" className="rounded-lg border border-border/60 bg-muted/20 p-3 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <span id="pipeline-telemetry-title" className="font-semibold text-foreground flex items-center gap-1.5">
              <span>🚀</span>
              <span>Pipeline: {latestState.pipeline_id}</span>
              <span className="text-muted-foreground font-mono">({latestState.target_name})</span>
            </span>
            <span
              className={`rounded px-2 py-0.5 text-[11px] font-mono font-medium uppercase ${
                latestState.current_stage === 'completed'
                  ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                  : latestState.current_stage === 'rolled_back'
                  ? 'bg-destructive/10 text-destructive border border-destructive/20 font-bold'
                  : 'bg-indigo-500/10 text-indigo-500 border border-indigo-500/20'
              }`}
            >
              {latestState.current_stage}
            </span>
          </div>

          {/* Verification Findings */}
          {latestState.verification && latestState.verification.findings.length > 0 && (
            <div className="rounded border border-amber-500/20 bg-amber-500/10 p-2 text-[11px] text-amber-500 space-y-1">
              <div className="font-semibold">Verification Advisory Findings:</div>
              <ul className="list-disc pl-4 space-y-0.5">
                {latestState.verification.findings.map((finding) => (
                  <li key={finding.code}>
                    <span>{finding.message}</span>
                    {finding.next_action && (
                      <span className="block text-foreground/80 mt-0.5 font-medium">
                        Next Action: {finding.next_action}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Rollback Details */}
          {latestState.rollback && (
            <div className="rounded border border-destructive/30 bg-destructive/10 p-2 text-[11px] text-destructive space-y-1">
              <div className="font-bold flex items-center gap-1">
                <span>⚠️</span>
                <span>Atomic Transactional Rollback Triggered</span>
              </div>
              <p className="text-foreground/90">Reason: {latestState.rollback.reason}</p>
              <div className="font-mono text-[10px] text-muted-foreground">
                Reverted Agents: {latestState.rollback.reverted_agents.join(', ') || 'None'}
              </div>
              <div className="font-mono text-[10px] text-muted-foreground">
                Reverted Routines: {latestState.rollback.reverted_crons.join(', ') || 'None'}
              </div>
            </div>
          )}

          {/* Observed Facts */}
          {latestState.verification?.observed_state && (
            <div className="flex flex-wrap gap-2 text-[10px] font-mono text-muted-foreground pt-1 border-t border-border/30">
              {Object.entries(latestState.verification.observed_state).map(([k, v]) => (
                <span key={k} className="rounded bg-muted px-1.5 py-0.5">
                  {k}: {v}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Cloner Modal / Inline Form */}
      {cloningSource && (
        <section aria-labelledby="clone-form-title" className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 p-3 text-xs space-y-2">
          <div className="flex items-center justify-between">
            <span id="clone-form-title" className="font-semibold text-foreground">
              Clone Agent: <span className="font-mono text-indigo-400">{cloningSource}</span>
            </span>
            <button
              type="button"
              onClick={() => setCloningSource(null)}
              className="text-muted-foreground hover:text-foreground text-xs"
            >
              ✕
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            System prompts and identity tokens will be sanitized to align with the new agent identity.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label htmlFor="clone-target-name-input" className="block text-[11px] font-medium text-foreground mb-1">
                New Target Name (kebab-case)
              </label>
              <input
                id="clone-target-name-input"
                type="text"
                value={cloneTargetName}
                onChange={(e) => setCloneTargetName(e.target.value)}
                className="w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <div>
              <label htmlFor="clone-display-name-input" className="block text-[11px] font-medium text-foreground mb-1">
                New Display Name
              </label>
              <input
                id="clone-display-name-input"
                type="text"
                value={cloneDisplayName}
                onChange={(e) => setCloneDisplayName(e.target.value)}
                className="w-full rounded border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          </div>
          <button
            type="button"
            disabled={isProcessing || !cloneTargetName.trim()}
            onClick={handleConfirmClone}
            className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
          >
            {isProcessing ? 'Sanitizing & Cloning...' : 'Confirm Clone'}
          </button>
        </section>
      )}

      {/* Catalog List */}
      <section aria-labelledby="active-catalog-title" className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 id="active-catalog-title" className="text-xs font-semibold text-foreground uppercase tracking-wider">
            Active Provisioned Agents ({catalog.length})
          </h3>
        </div>

        {catalog.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/60 p-6 text-center text-xs text-muted-foreground">
            No active agents provisioned yet. Create one via Agent Forge or Team Squad.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2.5">
            {catalog.map((agent) => (
              <div
                key={agent.name}
                className="rounded-lg border border-border/50 bg-card p-3 text-xs space-y-2 transition-all hover:border-border"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground text-sm">{agent.display_name}</span>
                      <span className="font-mono text-xs text-muted-foreground">({agent.name})</span>
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                        {agent.model}
                      </span>
                      {agent.role_type === 'lead' && (
                        <span className="rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-1.5 py-0.5 text-[10px] font-mono">
                          LEAD
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground leading-normal">
                      {agent.description}
                    </p>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      disabled={isProcessing}
                      onClick={() => handleStartClone(agent)}
                      className="rounded border border-border/40 px-2 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
                      title="Clone agent"
                    >
                      Clone
                    </button>
                    <button
                      type="button"
                      disabled={isProcessing}
                      onClick={() => onDeleteAgent(agent.name)}
                      className="rounded border border-destructive/20 text-destructive px-2 py-1 text-[11px] font-medium hover:bg-destructive/10 transition-colors disabled:opacity-50"
                      title="Delete agent"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-muted-foreground pt-1 border-t border-border/30">
                  <span>Tools: {agent.tools.join(', ') || 'None'}</span>
                  {agent.skills.length > 0 && <span>• Skills: {agent.skills.join(', ')}</span>}
                  {agent.cron_routines.length > 0 && (
                    <span className="text-indigo-400 font-semibold">
                      • Cron: {agent.cron_routines.join(', ')}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
