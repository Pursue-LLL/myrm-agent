/**
 * [INPUT] @/lib/api::apiRequest
 * [OUTPUT] Milestone CRUD API 封装
 * [POS] 里程碑管理 API 服务层。封装里程碑增删改查、进度查询、路线图摘要，以及评估导入候选工件读取。
 */

import { apiRequest } from '@/lib/api';

export interface Milestone {
  id: string;
  projectId: string;
  title: string;
  description: string;
  status: 'active' | 'completed' | 'archived';
  sortOrder: number;
  acceptanceCriteria: string;
  createdAt: string | null;
  updatedAt: string | null;
  completedAt: string | null;
}

export interface MilestoneProgress {
  milestoneId: string;
  totalTasks: number;
  completedTasks: number;
  progress: number;
}

export interface ProjectRoadmap {
  projectName: string;
  projectDescription: string;
  goalSummary: string;
  activeMilestones: Milestone[];
  completedMilestones: Milestone[];
  contextSnippet: string;
}

export interface AssessmentImportMilestoneReceipt {
  milestone_id: string;
  milestone_title: string;
  board_id: string;
  board_name: string;
  task_count: number;
}

export interface AssessmentImportReceipt {
  import_id: number;
  project_id: string;
  artifact_id: string;
  artifact_version_id: string;
  source_chat_id: string | null;
  imported_milestones: AssessmentImportMilestoneReceipt[];
  total_milestones: number;
  total_tasks: number;
  imported_at: string;
}

export interface AssessmentImportArtifactCandidate {
  id: string;
  name: string;
  updated_at: string;
  latest_version_id: string | null;
}

interface ArtifactListItem {
  id?: string;
  name?: string;
  updated_at?: string;
  latest_version_id?: string;
}

function parseTimestamp(value: string): number {
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export function normalizeAssessmentImportArtifactCandidates(
  artifacts: ArtifactListItem[],
  limit = 8,
): AssessmentImportArtifactCandidate[] {
  const cappedLimit = Math.max(1, limit);
  const normalized: AssessmentImportArtifactCandidate[] = [];
  for (const artifact of artifacts) {
    const id = typeof artifact.id === 'string' ? artifact.id.trim() : '';
    if (!id) {
      continue;
    }
    const nameValue = typeof artifact.name === 'string' ? artifact.name.trim() : '';
    const updatedAtValue = typeof artifact.updated_at === 'string' ? artifact.updated_at.trim() : '';
    const latestVersionValue =
      typeof artifact.latest_version_id === 'string' ? artifact.latest_version_id.trim() : '';
    normalized.push({
      id,
      name: nameValue || id,
      updated_at: updatedAtValue,
      latest_version_id: latestVersionValue || null,
    });
  }
  normalized.sort((left, right) => parseTimestamp(right.updated_at) - parseTimestamp(left.updated_at));
  return normalized.slice(0, cappedLimit);
}

export const getMilestones = async (projectId: string, includeArchived = false): Promise<Milestone[]> => {
  const params = includeArchived ? '?include_archived=true' : '';
  const data = (await apiRequest(`/projects/${projectId}/milestones${params}`)) as { milestones?: Milestone[] };
  return data.milestones ?? [];
};

export const createMilestone = async (
  projectId: string,
  payload: { title: string; description?: string; acceptance_criteria?: string },
): Promise<Milestone> => {
  const data = (await apiRequest(`/projects/${projectId}/milestones`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })) as { milestone: Milestone };
  return data.milestone;
};

export const updateMilestone = async (
  projectId: string,
  milestoneId: string,
  payload: { title?: string; description?: string; acceptance_criteria?: string; status?: string },
): Promise<Milestone> => {
  const data = (await apiRequest(`/projects/${projectId}/milestones/${milestoneId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })) as { milestone: Milestone };
  return data.milestone;
};

export const deleteMilestone = async (projectId: string, milestoneId: string): Promise<void> => {
  await apiRequest(`/projects/${projectId}/milestones/${milestoneId}`, { method: 'DELETE' });
};

export const getMilestoneProgress = async (projectId: string, milestoneId: string): Promise<MilestoneProgress> => {
  const data = (await apiRequest(`/projects/${projectId}/milestones/${milestoneId}/progress`)) as {
    progress: MilestoneProgress;
  };
  return data.progress;
};

export const getProjectRoadmap = async (projectId: string): Promise<ProjectRoadmap> => {
  const data = (await apiRequest(`/projects/${projectId}/roadmap`)) as { roadmap: ProjectRoadmap };
  return data.roadmap;
};

export const importAssessmentArtifact = async (
  projectId: string,
  payload: {
    artifact_id: string;
    source_chat_id?: string;
    max_milestones?: number;
    max_tasks_per_milestone?: number;
  },
): Promise<AssessmentImportReceipt> => {
  const data = (await apiRequest(`/projects/${projectId}/milestones/import-assessment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })) as { receipt: AssessmentImportReceipt };
  return data.receipt;
};

export const listAssessmentImportArtifactCandidates = async (
  limit = 8,
): Promise<AssessmentImportArtifactCandidate[]> => {
  const cappedLimit = Math.min(Math.max(1, limit), 500);
  const data = (await apiRequest(`/files/artifacts?limit=${cappedLimit}`)) as {
    artifacts?: ArtifactListItem[];
  };
  return normalizeAssessmentImportArtifactCandidates(data.artifacts ?? [], limit);
};
