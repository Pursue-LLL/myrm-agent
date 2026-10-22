import {
  ArtifactForkBranch,
  DiffLine,
  RelayStage,
  StageArtifactSnapshot,
} from './multiRoleRelayTypes';

export interface RelayProgressSummary {
  total: number;
  completed: number;
  progressPercent: number;
  activeRole?: string;
  isFinished: boolean;
}

export function calculateRelayProgress(stages: RelayStage[]): RelayProgressSummary {
  if (stages.length === 0) {
    return {
      total: 0,
      completed: 0,
      progressPercent: 0,
      isFinished: false,
    };
  }

  const completed = stages.filter((s) => s.status === 'completed').length;
  const inProgressStage = stages.find((s) => s.status === 'in_progress');
  const progressPercent = Math.round((completed / stages.length) * 100);
  const isFinished = completed === stages.length;

  return {
    total: stages.length,
    completed,
    progressPercent,
    activeRole: inProgressStage ? inProgressStage.roleName : undefined,
    isFinished,
  };
}

export function computeContentDiffLines(
  original: string,
  modified: string
): DiffLine[] {
  const origLines = original.split('\n');
  const modLines = modified.split('\n');
  const diff: DiffLine[] = [];

  const maxLen = Math.max(origLines.length, modLines.length);

  for (let i = 0; i < maxLen; i++) {
    const oLine = origLines[i];
    const mLine = modLines[i];

    if (oLine === undefined && mLine !== undefined) {
      diff.push({ type: 'added', text: mLine, lineNumber: i + 1 });
    } else if (oLine !== undefined && mLine === undefined) {
      diff.push({ type: 'removed', text: oLine, lineNumber: i + 1 });
    } else if (oLine !== mLine) {
      diff.push({ type: 'removed', text: oLine, lineNumber: i + 1 });
      diff.push({ type: 'added', text: mLine, lineNumber: i + 1 });
    } else {
      diff.push({ type: 'unchanged', text: oLine, lineNumber: i + 1 });
    }
  }

  return diff;
}

export function createArtifactForkBranch(
  snapshot: StageArtifactSnapshot,
  branchName: string,
  modifiedContent: string,
  userNote?: string
): ArtifactForkBranch {
  return {
    id: `fork-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    baseSnapshotId: snapshot.id,
    stageId: snapshot.stageId,
    branchName: branchName.trim() || `branch-v${snapshot.version + 1}`,
    modifiedContent,
    userNote,
    createdAt: Date.now(),
    status: 'draft',
  };
}

export function advanceRelayPipeline(
  stages: RelayStage[],
  currentStageId: string,
  outputSnapshot?: StageArtifactSnapshot
): RelayStage[] {
  const currentIndex = stages.findIndex((s) => s.id === currentStageId);
  if (currentIndex === -1) {
    return stages;
  }

  return stages.map((stage, idx) => {
    if (idx === currentIndex) {
      return {
        ...stage,
        status: 'completed',
        completedAt: Date.now(),
        snapshot: outputSnapshot || stage.snapshot,
      };
    }
    if (idx === currentIndex + 1 && stage.status === 'pending') {
      return {
        ...stage,
        status: 'in_progress',
        startedAt: Date.now(),
      };
    }
    return stage;
  });
}
