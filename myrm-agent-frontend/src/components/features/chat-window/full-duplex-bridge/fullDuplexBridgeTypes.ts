export type BackgroundWorkerStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'canceled';

export type StepNodeStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface WorkerStepNode {
  id: string;
  label: string;
  status: StepNodeStatus;
  timestamp?: string;
  detail?: string;
}

export type ArtifactType = 'report' | 'code' | 'video' | 'data';

export interface WorkerArtifactPayload {
  id: string;
  title: string;
  type: ArtifactType;
  summary: string;
  artifactUrl?: string;
  previewSnippet?: string;
}

export interface BackgroundWorkerTask {
  id: string;
  title: string;
  category: string;
  status: BackgroundWorkerStatus;
  progress: number; // 0 - 100
  currentStepLabel: string;
  steps: WorkerStepNode[];
  elapsedSec: number;
  estimatedTotalSec: number;
  spawnedAt: number;
  completedAt?: number;
  artifact?: WorkerArtifactPayload;
  errorMessage?: string;
}

export interface ReanchoredResultCard {
  id: string;
  workerId: string;
  title: string;
  category: string;
  elapsedSec: number;
  artifact: WorkerArtifactPayload;
  targetMessageAnchorId?: string;
  isAdopted: boolean;
  createdAt: number;
}

export interface SpawnWorkerParams {
  id?: string;
  title: string;
  category?: string;
  estimatedTotalSec?: number;
  stepLabels?: string[];
}
