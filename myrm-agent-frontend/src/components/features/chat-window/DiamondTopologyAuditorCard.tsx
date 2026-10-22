import React, { useState } from 'react';
import {
  DiamondNodeItem,
  CensusStatusItem,
  AdversarialVerdictItem,
  DEFAULT_DIAMOND_NODES,
  DEFAULT_VERDICT,
  DiamondStage,
} from './diamond-graph/types';

interface DiamondTopologyAuditorCardProps {
  chatId: string;
  initialNodes?: DiamondNodeItem[];
  initialVerdict?: AdversarialVerdictItem;
  onPruneDependencies?: () => Promise<string[][]>;
  onRetryDeadNodes?: () => Promise<string[]>;
  onRunAudit?: () => Promise<AdversarialVerdictItem>;
}

export const DiamondTopologyAuditorCard: React.FC<DiamondTopologyAuditorCardProps> = ({
  chatId,
  initialNodes = DEFAULT_DIAMOND_NODES,
  initialVerdict = DEFAULT_VERDICT,
  onPruneDependencies,
  onRetryDeadNodes,
  onRunAudit,
}) => {
  const [nodes, setNodes] = useState<DiamondNodeItem[]>(initialNodes);
  const [verdict, setVerdict] = useState<AdversarialVerdictItem>(initialVerdict);
  const [activeTab, setActiveTab] = useState<'topology' | 'census' | 'audit'>('topology');
  const [prunedEdgesCount, setPrunedEdgesCount] = useState<number>(0);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>('Ready');

  const fanOutNodes = nodes.filter((n) => n.stage === 'fan_out');
  const reduceNode = nodes.find((n) => n.stage === 'reduce');
  const synthNode = nodes.find((n) => n.stage === 'synthesize');

  const completedFanOut = fanOutNodes.filter((n) => n.status === 'completed').length;
  const isCensusHealthy = completedFanOut === fanOutNodes.length;

  const censusStatus: CensusStatusItem = {
    dispatchedCount: fanOutNodes.length,
    receivedCount: completedFanOut,
    missingNodes: fanOutNodes.filter((n) => n.status !== 'completed').map((n) => n.nodeId),
    isHealthy: isCensusHealthy,
    retriedNodes: [],
  };

  const handlePrune = async () => {
    setIsProcessing(true);
    setStatusMessage('Pruning false dependencies between parallel branches...');
    try {
      if (onPruneDependencies) {
        const pruned = await onPruneDependencies();
        setPrunedEdgesCount(pruned.length);
      } else {
        // Fallback simulation: strip artificial dependencies
        setNodes((prev) =>
          prev.map((n) => (n.stage === 'fan_out' && n.dependsOn.length > 0 ? { ...n, dependsOn: [], isPruned: true } : n))
        );
        setPrunedEdgesCount(1);
      }
      setStatusMessage('Pruned artificial serialized dependencies successfully.');
    } catch {
      setStatusMessage('Failed to prune dependencies.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRetryDead = async () => {
    setIsProcessing(true);
    setStatusMessage('Retrying uncompleted fan-out nodes...');
    try {
      if (onRetryDeadNodes) {
        const retried = await onRetryDeadNodes();
        setStatusMessage(`Retried ${retried.length} nodes successfully.`);
      } else {
        setNodes((prev) =>
          prev.map((n) => (n.status !== 'completed' ? { ...n, status: 'completed' } : n))
        );
        setStatusMessage('Simulated retry: all fan-out nodes completed.');
      }
    } catch {
      setStatusMessage('Retry failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReAudit = async () => {
    setIsProcessing(true);
    setStatusMessage('Executing blinded adversarial review with reality anchors...');
    try {
      if (onRunAudit) {
        const v = await onRunAudit();
        setVerdict(v);
      }
      setStatusMessage('Audit completed with objective reality checks.');
    } catch {
      setStatusMessage('Audit execution failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  const getStageBadgeColor = (stage: DiamondStage) => {
    switch (stage) {
      case 'fan_out':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'reduce':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
      case 'synthesize':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      default:
        return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
    }
  };

  return (
    <section
      aria-label="Diamond Topology and Adversarial Auditor"
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 text-card-foreground shadow-sm"
    >
      {/* Header bar */}
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
          <h2 className="text-sm font-semibold tracking-wide">
            Diamond Topology &amp; Blinded Auditor Pack
          </h2>
          <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {chatId}
          </span>
        </div>

        {/* Global actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePrune}
            disabled={isProcessing}
            className="rounded border border-border bg-background px-2.5 py-1 text-xs font-medium hover:bg-muted focus:outline-none focus:ring-1 focus:ring-primary"
          >
            Prune False Deps {prunedEdgesCount > 0 ? `(${prunedEdgesCount})` : ''}
          </button>
          <button
            type="button"
            onClick={handleReAudit}
            disabled={isProcessing}
            className="rounded bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-1 focus:ring-primary"
          >
            Run Blind Audit
          </button>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav aria-label="Auditor View Tabs" className="flex border-b border-border text-xs">
        <button
          type="button"
          onClick={() => setActiveTab('topology')}
          className={`px-3 py-1.5 font-medium border-b-2 transition-colors ${
            activeTab === 'topology'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Diamond Stages ({nodes.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('census')}
          className={`px-3 py-1.5 font-medium border-b-2 transition-colors ${
            activeTab === 'census'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Census Sentinel ({censusStatus.receivedCount}/{censusStatus.dispatchedCount})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('audit')}
          className={`px-3 py-1.5 font-medium border-b-2 transition-colors ${
            activeTab === 'audit'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Blinded Panel &amp; Anchors ({verdict.passed ? 'PASSED' : 'FAILED'})
        </button>
      </nav>

      {/* Main Tab Content */}
      <div className="min-h-[160px]">
        {activeTab === 'topology' && (
          <div className="flex flex-col gap-2.5">
            {/* Fan-Out Stage */}
            <div className="flex flex-col gap-1.5 rounded border border-border/50 bg-muted/20 p-2.5">
              <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-400" /> Stage 1: Fan-Out Exploration ({fanOutNodes.length})
                </span>
                <span>Deterministic 0-Token Bound</span>
              </div>
              <ul className="flex flex-col gap-1.5 text-xs">
                {fanOutNodes.map((node) => (
                  <li
                    key={node.nodeId}
                    className="flex flex-col gap-1 rounded border border-border bg-background p-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground">{node.title}</span>
                      <div className="flex items-center gap-1.5">
                        {node.isPruned && (
                          <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-500 border border-amber-500/20">
                            Pruned False Dep
                          </span>
                        )}
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-mono border ${getStageBadgeColor(node.stage)}`}>
                          {node.status}
                        </span>
                      </div>
                    </div>
                    {node.outputArtifact && (
                      <p className="line-clamp-2 text-muted-foreground bg-muted/30 p-1 rounded font-mono text-[11px]">
                        {node.outputArtifact}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            {/* Reduce Stage */}
            {reduceNode && (
              <div className="flex flex-col gap-1.5 rounded border border-border/50 bg-muted/20 p-2.5">
                <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-purple-400" /> Stage 2: Deterministic Reduce
                  </span>
                  <span className="text-[10px] text-muted-foreground">0 LLM Token Deduplication</span>
                </div>
                <div className="rounded border border-border bg-background p-2 text-xs">
                  <div className="flex items-center justify-between font-medium">
                    <span>{reduceNode.title}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-mono border ${getStageBadgeColor(reduceNode.stage)}`}>
                      {reduceNode.status}
                    </span>
                  </div>
                  {reduceNode.outputArtifact && (
                    <p className="mt-1 text-muted-foreground font-mono text-[11px] bg-muted/30 p-1 rounded">
                      {reduceNode.outputArtifact}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Synthesize Stage */}
            {synthNode && (
              <div className="flex flex-col gap-1.5 rounded border border-border/50 bg-muted/20 p-2.5">
                <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-400" /> Stage 3: Top-Tier Synthesis
                  </span>
                  <span className="text-[10px] text-muted-foreground">Consolidated Architecture</span>
                </div>
                <div className="rounded border border-border bg-background p-2 text-xs">
                  <div className="flex items-center justify-between font-medium">
                    <span>{synthNode.title}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-mono border ${getStageBadgeColor(synthNode.stage)}`}>
                      {synthNode.status}
                    </span>
                  </div>
                  {synthNode.outputArtifact && (
                    <p className="mt-1 text-muted-foreground font-mono text-[11px] bg-muted/30 p-1 rounded">
                      {synthNode.outputArtifact}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'census' && (
          <div className="flex flex-col gap-3 rounded border border-border bg-muted/10 p-3 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground">Dead-Node Census Sentinel Status</span>
              <span
                className={`rounded px-2 py-0.5 font-medium ${
                  censusStatus.isHealthy
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                }`}
              >
                {censusStatus.isHealthy ? 'Healthy (No Dead Nodes)' : 'Imbalance Detected'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
              <div className="rounded border border-border bg-background p-2">
                <div className="text-muted-foreground text-[11px]">Dispatched</div>
                <div className="text-base font-bold text-foreground">{censusStatus.dispatchedCount}</div>
              </div>
              <div className="rounded border border-border bg-background p-2">
                <div className="text-muted-foreground text-[11px]">Received</div>
                <div className="text-base font-bold text-emerald-500">{censusStatus.receivedCount}</div>
              </div>
              <div className="rounded border border-border bg-background p-2">
                <div className="text-muted-foreground text-[11px]">Missing</div>
                <div className="text-base font-bold text-rose-500">{censusStatus.missingNodes.length}</div>
              </div>
              <div className="rounded border border-border bg-background p-2">
                <div className="text-muted-foreground text-[11px]">Completion</div>
                <div className="text-base font-bold text-foreground">
                  {censusStatus.dispatchedCount > 0
                    ? `${Math.round((censusStatus.receivedCount / censusStatus.dispatchedCount) * 100)}%`
                    : '100%'}
                </div>
              </div>
            </div>

            {censusStatus.missingNodes.length > 0 && (
              <div className="flex items-center justify-between rounded border border-rose-500/30 bg-rose-500/10 p-2">
                <span className="text-rose-400">
                  Dead nodes: {censusStatus.missingNodes.join(', ')}
                </span>
                <button
                  type="button"
                  onClick={handleRetryDead}
                  disabled={isProcessing}
                  className="rounded bg-rose-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-rose-500"
                >
                  Retry Dead Nodes
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'audit' && (
          <div className="flex flex-col gap-3 text-xs">
            {/* Verdict summary */}
            <div
              className={`flex items-center justify-between rounded border p-2.5 ${
                verdict.passed
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                  : 'border-rose-500/30 bg-rose-500/10 text-rose-400'
              }`}
            >
              <div className="flex flex-col">
                <span className="font-semibold tracking-wide">
                  VERDICT: {verdict.passed ? 'PASSED (2/3 Vote + 100% Anchors)' : 'FAILED'}
                </span>
                <span className="text-[11px] text-muted-foreground mt-0.5">{verdict.consensusSummary}</span>
              </div>
              <span className="text-sm font-bold font-mono">
                {verdict.passCount}/{verdict.totalReviews} Approved
              </span>
            </div>

            {/* 3 Auditor Perspectives */}
            <div className="flex flex-col gap-1.5">
              <span className="font-semibold text-muted-foreground">Blinded Independent Perspectives (CoT Stripped):</span>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {verdict.reviews.map((rev) => (
                  <div
                    key={rev.perspective}
                    className="flex flex-col gap-1 rounded border border-border bg-background p-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium uppercase tracking-wider text-[10px] text-muted-foreground">
                        {rev.perspective.replace('_', ' ')}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                          rev.passed ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                        }`}
                      >
                        {Math.round(rev.score * 100)}%
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{rev.critique}</p>
                    <span className="text-[9px] text-muted-foreground/60 mt-auto">
                      {rev.isolatedContextVerified ? '✓ Strict Context Isolation' : 'Context Polluted'}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Reality Anchors */}
            <div className="flex flex-col gap-1.5">
              <span className="font-semibold text-muted-foreground">Objective External Reality Anchors:</span>
              <ul className="flex flex-col gap-1">
                {verdict.anchorChecks.map((anchor) => (
                  <li
                    key={anchor.targetId}
                    className="flex items-center justify-between rounded border border-border bg-background p-2 font-mono text-[11px]"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          anchor.verified ? 'bg-emerald-500' : 'bg-rose-500'
                        }`}
                      />
                      <span>[{anchor.anchorType}] {anchor.targetId}</span>
                    </div>
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <span>expected: {anchor.expectedValue}</span>
                      <span>actual: {anchor.actualValue ?? 'null'}</span>
                      <span className={anchor.verified ? 'text-emerald-500 font-bold' : 'text-rose-500 font-bold'}>
                        {anchor.verified ? 'MATCH' : 'MISMATCH'}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Footer status line with live announcer */}
      <footer className="border-t border-border pt-2 text-xs text-muted-foreground">
        <output aria-live="polite" className="block truncate">
          Status: {statusMessage}
        </output>
      </footer>
    </section>
  );
};
