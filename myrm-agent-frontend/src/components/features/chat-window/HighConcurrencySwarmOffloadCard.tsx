import React, { useState, useMemo } from 'react';
import {
  Cpu,
  Cloud,
  Laptop,
  Activity,
  Zap,
  Play,
  X,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Layers,
  HardDrive,
} from 'lucide-react';
import {
  HighConcurrencySwarmOffloadCardProps,
  INITIAL_WATERMARK,
  INITIAL_WORKERS,
  OffloadStrategyType,
  ResourceWatermarkSnapshot,
  SwarmBatchItem,
  SwarmWorkerItem,
} from './swarm-offload/types';

export * from './swarm-offload/types';

export function HighConcurrencySwarmOffloadCard({
  batchId = 'batch-swarm-alpha-12',
  onDismiss,
  onBatchDispatched,
}: HighConcurrencySwarmOffloadCardProps): React.ReactElement {
  const [strategy, setStrategy] = useState<OffloadStrategyType>('adaptive');
  const [watermark, setWatermark] = useState<ResourceWatermarkSnapshot>(INITIAL_WATERMARK);
  const [workers, setWorkers] = useState<SwarmWorkerItem[]>(INITIAL_WORKERS);
  const [isSimulating, setIsSimulating] = useState(false);

  const localCount = useMemo(() => {
    return workers.filter((w) => w.target === 'local_host').length;
  }, [workers]);

  const cloudCount = useMemo(() => {
    return workers.filter((w) => w.target === 'cloud_sandbox').length;
  }, [workers]);

  const handleStrategyChange = (newStrat: OffloadStrategyType) => {
    setStrategy(newStrat);
    if (newStrat === 'force_cloud') {
      setWorkers((prev) =>
        prev.map((w) => ({
          ...w,
          target: 'cloud_sandbox' as const,
          artifactPointer: w.artifactPointer || `vault://artifacts/${w.taskId}/result.bin`,
        }))
      );
    } else if (newStrat === 'force_local') {
      setWorkers((prev) =>
        prev.map((w) => ({
          ...w,
          target: 'local_host' as const,
        }))
      );
    } else {
      setWorkers(INITIAL_WORKERS);
    }
  };

  const handleSimulateDispatch = () => {
    setIsSimulating(true);

    const updatedWm: ResourceWatermarkSnapshot = {
      ...watermark,
      cpuPercent: strategy === 'force_local' ? 94.0 : 48.0,
      memoryPercent: strategy === 'force_local' ? 89.0 : 58.0,
      activeLocalWorkers: strategy === 'force_cloud' ? 0 : strategy === 'force_local' ? 12 : 4,
      isOverWatermark: strategy === 'force_local',
      recommendation: strategy === 'force_local' ? 'cloud_sandbox' : 'local_host',
    };
    setWatermark(updatedWm);

    const remappedWorkers = INITIAL_WORKERS.map((w, idx) => {
      let target: 'local_host' | 'cloud_sandbox' = 'cloud_sandbox';
      if (strategy === 'force_local') {
        target = 'local_host';
      } else if (strategy === 'force_cloud') {
        target = 'cloud_sandbox';
      } else {
        target = idx < 4 ? 'local_host' : 'cloud_sandbox';
      }
      return {
        ...w,
        target,
        durationMs: target === 'local_host' ? 40 + idx * 8 : 800 + idx * 110,
        artifactPointer: target === 'cloud_sandbox' ? `vault://artifacts/${w.taskId}/out.parquet` : undefined,
      };
    });

    setWorkers(remappedWorkers);
    setIsSimulating(false);

    const batchSummary: SwarmBatchItem = {
      batchId,
      totalTasks: remappedWorkers.length,
      localCount: remappedWorkers.filter((w) => w.target === 'local_host').length,
      cloudCount: remappedWorkers.filter((w) => w.target === 'cloud_sandbox').length,
      completedCount: remappedWorkers.length,
      failedCount: 0,
      avgDurationMs: 650,
      peakCpuPercent: updatedWm.cpuPercent,
      peakMemoryPercent: updatedWm.memoryPercent,
      strategy,
      workers: remappedWorkers,
    };
    onBatchDispatched?.(batchSummary);
  };

  return (
    <section
      aria-label="High-Concurrency Subagent Swarm Cockpit"
      className="rounded-xl border border-border/80 bg-card/95 p-4 shadow-xl backdrop-blur-md transition-all text-card-foreground my-3"
    >
      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center space-x-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-500 ring-1 ring-indigo-500/20">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm">High-Concurrency Subagent Swarm (10–15 Workers)</span>
              <span className="inline-flex items-center rounded-full bg-indigo-500/10 px-2 py-0.5 text-[11px] font-medium text-indigo-500 border border-indigo-500/20">
                Item 60 Active
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-mono">
              Batch: {batchId} · Transparent Cloud Sandbox Offload & Physical Laptop Safeguard
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {onDismiss && (
            <button
              onClick={onDismiss}
              aria-label="Close Swarm Cockpit"
              className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2.5">
        <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 text-xs">
          <div className="flex items-center justify-between text-muted-foreground mb-1">
            <span className="flex items-center gap-1">
              <Cpu className="h-3.5 w-3.5 text-primary" />
              <span>Host CPU Load</span>
            </span>
            <span className="font-mono font-medium text-foreground">{watermark.cpuPercent}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                watermark.cpuPercent >= watermark.cpuThresholdPercent ? 'bg-amber-500' : 'bg-primary'
              }`}
              style={{ width: `${Math.min(100, watermark.cpuPercent)}%` }}
            />
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Threshold: {watermark.cpuThresholdPercent}%</p>
        </div>

        <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 text-xs">
          <div className="flex items-center justify-between text-muted-foreground mb-1">
            <span className="flex items-center gap-1">
              <HardDrive className="h-3.5 w-3.5 text-primary" />
              <span>Host Memory Load</span>
            </span>
            <span className="font-mono font-medium text-foreground">{watermark.memoryPercent}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                watermark.memoryPercent >= watermark.memoryThresholdPercent ? 'bg-amber-500' : 'bg-primary'
              }`}
              style={{ width: `${Math.min(100, watermark.memoryPercent)}%` }}
            />
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Threshold: {watermark.memoryThresholdPercent}%</p>
        </div>

        <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 text-xs flex flex-col justify-between">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="flex items-center gap-1">
              <Activity className="h-3.5 w-3.5 text-primary" />
              <span>Local Worker Load</span>
            </span>
            <span className="font-mono font-medium text-foreground">
              {watermark.activeLocalWorkers} / {watermark.maxRecommendedLocalWorkers}
            </span>
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <span
              className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                watermark.isOverWatermark
                  ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                  : 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
              }`}
            >
              {watermark.isOverWatermark ? (
                <>
                  <AlertTriangle className="h-2.5 w-2.5" />
                  <span>OVER-WATERMARK</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="h-2.5 w-2.5" />
                  <span>SAFE CAPACITY</span>
                </>
              )}
            </span>
            <span className="text-[10px] text-muted-foreground font-mono">Target: {watermark.recommendation}</span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-y border-border/40 py-2.5 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground font-medium">Offload Policy:</span>
          <div className="flex rounded-md bg-muted/60 p-0.5">
            <button
              onClick={() => {
                handleStrategyChange('adaptive');
              }}
              className={`rounded px-2.5 py-1 font-medium transition-colors ${
                strategy === 'adaptive'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Adaptive Offload
            </button>
            <button
              onClick={() => {
                handleStrategyChange('force_local');
              }}
              className={`rounded px-2.5 py-1 font-medium transition-colors ${
                strategy === 'force_local'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Force Local
            </button>
            <button
              onClick={() => {
                handleStrategyChange('force_cloud');
              }}
              className={`rounded px-2.5 py-1 font-medium transition-colors ${
                strategy === 'force_cloud'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Force Cloud
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 text-[11px] font-mono text-muted-foreground">
            <span className="flex items-center gap-1 text-primary">
              <Laptop className="h-3 w-3" />
              <span>{localCount} Local</span>
            </span>
            <span>·</span>
            <span className="flex items-center gap-1 text-indigo-500">
              <Cloud className="h-3 w-3" />
              <span>{cloudCount} Cloud</span>
            </span>
          </div>
          <button
            onClick={handleSimulateDispatch}
            disabled={isSimulating}
            className="inline-flex items-center gap-1 rounded bg-primary px-3 py-1 font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
          >
            <Play className="h-3 w-3" />
            <span>Dispatch 12-Worker Swarm</span>
          </button>
        </div>
      </div>

      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
          <span className="font-medium">Active Concurrent Worker Swarm Grid ({workers.length})</span>
          <span className="text-[11px] font-mono">Zero-Overhead Harness Pipeline</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {workers.map((worker) => (
            <div
              key={worker.workerId}
              className="rounded-lg border border-border/50 bg-background/50 p-2.5 text-xs flex flex-col justify-between space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-foreground truncate pr-1">{worker.title}</span>
                <span
                  className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono uppercase ${
                    worker.target === 'cloud_sandbox'
                      ? 'bg-indigo-500/10 text-indigo-500 border border-indigo-500/20'
                      : 'bg-sky-500/10 text-sky-500 border border-sky-500/20'
                  }`}
                >
                  {worker.target === 'cloud_sandbox' ? (
                    <>
                      <Cloud className="h-2.5 w-2.5" />
                      <span>CLOUD</span>
                    </>
                  ) : (
                    <>
                      <Laptop className="h-2.5 w-2.5" />
                      <span>LOCAL</span>
                    </>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                <span>{worker.workerId}</span>
                <div className="flex items-center gap-1 text-emerald-500">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>{worker.durationMs}ms</span>
                </div>
              </div>
              {worker.artifactPointer && (
                <div className="pt-1 border-t border-border/30 text-[10px] font-mono text-primary truncate">
                  <span className="text-muted-foreground">Ptr: </span>
                  <span>{worker.artifactPointer}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default HighConcurrencySwarmOffloadCard;
