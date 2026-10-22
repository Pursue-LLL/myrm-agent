import React, { useState } from 'react';
import {
  BatchDispatchResult,
  BatchDispatchTask,
  DEFAULT_EXTERNAL_BUNDLES,
  DEFAULT_INSTANCES,
  ExternalBundleProfileSpec,
  ProbeBundleResponse,
  SubagentInstanceRecord,
  TerminateInstanceResult,
} from './external-bundle/types';
import { BundleHeaderView, ExternalBundleTab } from './external-bundle/BundleHeaderView';
import { BundleCatalogView } from './external-bundle/BundleCatalogView';
import { BatchDispatchView } from './external-bundle/BatchDispatchView';
import { InstanceMultiplexMonitorView } from './external-bundle/InstanceMultiplexMonitorView';

export interface ExternalAgentBundleManagerCardProps {
  chatId: string;
  initialBundles?: ExternalBundleProfileSpec[];
  initialInstances?: SubagentInstanceRecord[];
  onProbeBundle?: (bundleId: string) => Promise<ProbeBundleResponse>;
  onDispatchBatch?: (tasks: BatchDispatchTask[], workspaceRoot?: string) => Promise<BatchDispatchResult>;
  onTerminateInstance?: (instanceId: string, reason?: string) => Promise<TerminateInstanceResult>;
  onRefresh?: () => Promise<void>;
}

export const ExternalAgentBundleManagerCard: React.FC<ExternalAgentBundleManagerCardProps> = ({
  chatId,
  initialBundles = DEFAULT_EXTERNAL_BUNDLES,
  initialInstances = DEFAULT_INSTANCES,
  onProbeBundle,
  onDispatchBatch,
  onTerminateInstance,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<ExternalBundleTab>('catalog');
  const [bundles, setBundles] = useState<ExternalBundleProfileSpec[]>(initialBundles);
  const [instances, setInstances] = useState<SubagentInstanceRecord[]>(initialInstances);
  const [selectedBundleForDispatch, setSelectedBundleForDispatch] = useState<string | undefined>(undefined);
  const [probingBundleId, setProbingBundleId] = useState<string | null>(null);
  const [terminatingId, setTerminatingId] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>(
    'Subagent Bundle Manager ready: heterogeneous CLI adapters with lock-free multiplexer active.',
  );

  const activeInstancesCount = instances.filter(
    (i) => i.status === 'running' || i.status === 'pending',
  ).length;

  const handleProbeBundle = async (bundleId: string): Promise<void> => {
    setProbingBundleId(bundleId);
    setStatusMessage(`Probing host environment PATH for bundle '${bundleId}'...`);
    try {
      if (onProbeBundle) {
        const res = await onProbeBundle(bundleId);
        setBundles((prev) =>
          prev.map((b) =>
            b.bundle_id === bundleId
              ? { ...b, is_installed: res.is_installed, version: res.version }
              : b,
          ),
        );
        setStatusMessage(
          res.is_installed
            ? `Bundle '${bundleId}' verified on host: binary '${res.binary_name}' found (v${res.version}).`
            : `Warning: Binary '${res.binary_name}' not detected in system PATH.`,
        );
      } else {
        // Mock fallback probe
        setBundles((prev) =>
          prev.map((b) => (b.bundle_id === bundleId ? { ...b, is_installed: true } : b)),
        );
        setStatusMessage(`Probe confirmed executable for '${bundleId}'.`);
      }
    } catch (err) {
      setStatusMessage(`Error probing bundle '${bundleId}': ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setProbingBundleId(null);
    }
  };

  const handleSelectForDispatch = (bundleId: string) => {
    setSelectedBundleForDispatch(bundleId);
    setActiveTab('dispatch');
    setStatusMessage(`Switched to dispatch tab with bundle '${bundleId}' pre-selected.`);
  };

  const handleDispatchBatch = async (
    tasks: BatchDispatchTask[],
    workspaceRoot?: string,
  ): Promise<void> => {
    setIsProcessing(true);
    setStatusMessage(`Concurrently launching batch of ${tasks.length} subagents...`);
    try {
      if (onDispatchBatch) {
        const result = await onDispatchBatch(tasks, workspaceRoot);
        setInstances((prev) => [...result.dispatched_instances, ...prev]);
        setStatusMessage(
          `Successfully multiplexed ${result.total_dispatched} subagent instance(s) in batch '${result.batch_id}'.`,
        );
        setActiveTab('monitor');
      } else {
        // Fallback local dispatch simulation
        const mockNewInstances: SubagentInstanceRecord[] = tasks.map((t, idx) => ({
          instance_id: `inst-mock-${Date.now().toString().slice(-4)}-${idx}`,
          bundle_id: t.bundle_id,
          session_id: chatId,
          role_label: t.role_label,
          status: 'running',
          pid: 50000 + Math.floor(Math.random() * 10000),
          task_prompt: t.task_prompt,
          target_workdir: workspaceRoot || `/workspace/${t.target_subdir || 'root'}`,
          created_at: Date.now(),
          started_at: Date.now(),
          stdout_chunks: [`[${t.role_label}] Process started with shlex-escaped args...`],
          artifacts: [],
        }));
        setInstances((prev) => [...mockNewInstances, ...prev]);
        setStatusMessage(`Dispatched ${tasks.length} subagent instance(s) concurrently.`);
        setActiveTab('monitor');
      }
    } catch (err) {
      setStatusMessage(`Failed to dispatch batch: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleTerminateInstance = async (instanceId: string, reason = 'user_halted'): Promise<void> => {
    setTerminatingId(instanceId);
    setStatusMessage(`Terminating subagent instance '${instanceId}' (${reason})...`);
    try {
      if (onTerminateInstance) {
        const res = await onTerminateInstance(instanceId, reason);
        setInstances((prev) =>
          prev.map((inst) =>
            inst.instance_id === instanceId
              ? {
                  ...inst,
                  status: res.status,
                  completed_at: Date.now(),
                  stdout_chunks: [...inst.stdout_chunks, `[system] Instance terminated: ${reason}`],
                }
              : inst,
          ),
        );
        setStatusMessage(`Subagent instance '${instanceId}' halted.`);
      } else {
        setInstances((prev) =>
          prev.map((inst) =>
            inst.instance_id === instanceId
              ? {
                  ...inst,
                  status: 'terminated',
                  completed_at: Date.now(),
                  stdout_chunks: [...inst.stdout_chunks, `[system] Instance terminated: ${reason}`],
                }
              : inst,
          ),
        );
        setStatusMessage(`Instance '${instanceId}' terminated.`);
      }
    } catch (err) {
      setStatusMessage(`Failed to terminate instance '${instanceId}': ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setTerminatingId(null);
    }
  };

  const handleRefresh = async () => {
    if (!onRefresh) {
      return;
    }
    setIsProcessing(true);
    setStatusMessage('Refreshing external agent bundles and instances...');
    try {
      await onRefresh();
      setStatusMessage('Bundles and subagent telemetry updated.');
    } catch (err) {
      setStatusMessage(`Refresh failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <article
      aria-label="External Agent Bundle Manager Card"
      className="my-3 overflow-hidden rounded-xl border border-border/60 bg-background/95 p-4 shadow-sm backdrop-blur-sm space-y-4"
    >
      <BundleHeaderView
        activeTab={activeTab}
        onTabChange={setActiveTab}
        totalBundles={bundles.length}
        activeInstancesCount={activeInstancesCount}
        isProcessing={isProcessing}
        onRefresh={onRefresh ? handleRefresh : undefined}
      />

      <div className="rounded-lg bg-muted/30 px-3 py-2 text-xs border border-border/30">
        <output aria-live="polite" className="flex items-center gap-2 text-foreground/90">
          <span className="font-semibold text-primary">Status:</span>
          <span>{statusMessage}</span>
        </output>
      </div>

      {activeTab === 'catalog' && (
        <BundleCatalogView
          bundles={bundles}
          probingBundleId={probingBundleId}
          onProbeBundle={handleProbeBundle}
          onSelectForDispatch={handleSelectForDispatch}
        />
      )}

      {activeTab === 'dispatch' && (
        <BatchDispatchView
          bundles={bundles}
          initialBundleId={selectedBundleForDispatch}
          isDispatching={isProcessing}
          onDispatchBatch={handleDispatchBatch}
        />
      )}

      {activeTab === 'monitor' && (
        <InstanceMultiplexMonitorView
          instances={instances}
          terminatingId={terminatingId}
          onTerminateInstance={handleTerminateInstance}
        />
      )}
    </article>
  );
};
