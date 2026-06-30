/**
 * [INPUT] @/lib/api::apiRequest
 * [OUTPUT] Project CRUD API 封装
 * [POS] 项目管理 API 服务层。封装项目增删改查和会话归属管理。
 */

import { apiRequest } from '@/lib/api';

export interface Project {
  id: string;
  name: string;
  color: string;
  sortOrder: number;
  workspacePath?: string;
  createdAt: string | null;
  updatedAt: string | null;
}

export const getProjects = async (): Promise<Project[]> => {
  const data = (await apiRequest('/projects')) as { projects?: Project[] };
  return data.projects ?? [];
};

export const createProject = async (name: string, color?: string): Promise<Project> => {
  const data = (await apiRequest('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, ...(color ? { color } : {}) }),
  })) as { project: Project };
  return data.project;
};

export const updateProject = async (
  id: string,
  updates: { name?: string; color?: string; workspace_path?: string },
): Promise<Project> => {
  const data = (await apiRequest(`/projects/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })) as { project: Project };
  return data.project;
};

export const deleteProject = async (id: string): Promise<void> => {
  await apiRequest(`/projects/${id}`, { method: 'DELETE' });
};

export const moveChatToProject = async (chatId: string, projectId: string | null): Promise<void> => {
  await apiRequest(`/projects/chats/${chatId}/project`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projectId }),
  });
};

export const batchMoveChats = async (chatIds: string[], projectId: string | null): Promise<number> => {
  const data = (await apiRequest('/projects/chats/batch-move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chatIds, projectId }),
  })) as { movedCount: number };
  return data.movedCount;
};
