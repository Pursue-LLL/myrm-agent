export type OffloadStrategyType = 'adaptive' | 'force_local' | 'force_cloud';
export type ExecutionTargetType = 'local_host' | 'cloud_sandbox';
export type WorkerStateType = 'queued' | 'running' | 'completed' | 'failed' | 'timed_out';

export interface ResourceWatermarkSnapshot {
  cpuPercent: number;
  memoryPercent: number;
  activeLocalWorkers: number;
  maxRecommendedLocalWorkers: number;
  cpuThresholdPercent: number;
  memoryThresholdPercent: number;
  isOverWatermark: boolean;
  recommendation: ExecutionTargetType;
}

export interface SwarmWorkerItem {
  workerId: string;
  taskId: string;
  title: string;
  target: ExecutionTargetType;
  state: WorkerStateType;
  durationMs: number;
  artifactPointer?: string;
  error?: string;
}

export interface SwarmBatchItem {
  batchId: string;
  totalTasks: number;
  localCount: number;
  cloudCount: number;
  completedCount: number;
  failedCount: number;
  avgDurationMs: number;
  peakCpuPercent: number;
  peakMemoryPercent: number;
  strategy: OffloadStrategyType;
  workers: SwarmWorkerItem[];
}

export interface HighConcurrencySwarmOffloadCardProps {
  chatId?: string;
  batchId?: string;
  onDismiss?: () => void;
  onBatchDispatched?: (batch: SwarmBatchItem) => void;
}

export const INITIAL_WATERMARK: ResourceWatermarkSnapshot = {
  cpuPercent: 42.0,
  memoryPercent: 55.0,
  activeLocalWorkers: 2,
  maxRecommendedLocalWorkers: 4,
  cpuThresholdPercent: 80.0,
  memoryThresholdPercent: 80.0,
  isOverWatermark: false,
  recommendation: 'local_host',
};

export const INITIAL_WORKERS: SwarmWorkerItem[] = [
  {
    workerId: 'worker-01-loc',
    taskId: 'task-auth-spec',
    title: 'JWT Auth Unit Tests',
    target: 'local_host',
    state: 'completed',
    durationMs: 48,
  },
  {
    workerId: 'worker-02-loc',
    taskId: 'task-db-spec',
    title: 'Database Schema Tests',
    target: 'local_host',
    state: 'completed',
    durationMs: 62,
  },
  {
    workerId: 'worker-03-cld',
    taskId: 'task-heavy-cargo',
    title: 'Cargo Release Build',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 1420,
    artifactPointer: 'vault://artifacts/build-release.bin',
  },
  {
    workerId: 'worker-04-cld',
    taskId: 'task-bench-sweep',
    title: 'Micro-Benchmark Sweep (1000 iter)',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 980,
    artifactPointer: 'vault://artifacts/bench-results.json',
  },
  {
    workerId: 'worker-05-cld',
    taskId: 'task-ocr-pipeline',
    title: 'Heavy PDF Multi-Page OCR',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 1650,
    artifactPointer: 'vault://artifacts/ocr-extracted.jsonl',
  },
  {
    workerId: 'worker-06-loc',
    taskId: 'task-eslint-check',
    title: 'Frontend Oxlint Check',
    target: 'local_host',
    state: 'completed',
    durationMs: 35,
  },
  {
    workerId: 'worker-07-cld',
    taskId: 'task-crawling-tibo',
    title: 'Multi-Source Doc Ingestion',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 820,
    artifactPointer: 'vault://artifacts/scraped-corpus.parquet',
  },
  {
    workerId: 'worker-08-cld',
    taskId: 'task-sec-audit',
    title: 'Static AST Security Scanner',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 740,
    artifactPointer: 'vault://artifacts/sec-audit-report.sarif',
  },
  {
    workerId: 'worker-09-loc',
    taskId: 'task-typing-verify',
    title: 'Pyright Type Consistency',
    target: 'local_host',
    state: 'completed',
    durationMs: 90,
  },
  {
    workerId: 'worker-10-cld',
    taskId: 'task-e2e-headless',
    title: 'Headless Browser Playwright Lane',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 1890,
    artifactPointer: 'vault://artifacts/playwright-trace.zip',
  },
  {
    workerId: 'worker-11-cld',
    taskId: 'task-docker-sim',
    title: 'Container Compose Dry-run',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 1120,
    artifactPointer: 'vault://artifacts/compose-dryrun.log',
  },
  {
    workerId: 'worker-12-cld',
    taskId: 'task-load-fuzzing',
    title: 'Fuzz Testing 10k Iterations',
    target: 'cloud_sandbox',
    state: 'completed',
    durationMs: 2100,
    artifactPointer: 'vault://artifacts/fuzz-crash-dump.json',
  },
];
