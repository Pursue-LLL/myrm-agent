/**
 * [INPUT] @/lib/api::apiRequest
 * [OUTPUT] Milestone CRUD API 封装
 * [POS] 里程碑管理 API 服务层。封装里程碑增删改查、进度查询和路线图摘要。
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
  project_id: string;
  artifact_id: string;
  artifact_version_id: string;
  source_chat_id: string | null;
  imported_milestones: AssessmentImportMilestoneReceipt[];
  total_milestones: number;
  total_tasks: number;
  imported_at: string;
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
