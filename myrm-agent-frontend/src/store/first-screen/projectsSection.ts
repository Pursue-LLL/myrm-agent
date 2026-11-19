/**
 * [INPUT]
 * - @/services/projects::Project (type only; POS: one project of the sidebar project bar)
 * - @/lib/utils/typeUtils::isRecord (POS: guard for parsed JSON)
 *
 * [OUTPUT]
 * - encodeProjects / decodeProjects: the `projects` section, the project list of the sidebar.
 *
 * [POS]
 * Codec of the `projects` section. Encoding keeps the fields `Project` declares and nothing else the server may have sent;
 * decoding trusts nothing: an entry that is not shaped like a project is dropped.
 */
import type { Project } from '@/services/projects';
import { isRecord } from '@/lib/utils/typeUtils';

function encodeProject(project: Project): Project {
  return {
    id: project.id,
    name: project.name,
    description: project.description,
    color: project.color,
    sortOrder: project.sortOrder,
    workspacePath: project.workspacePath,
    workspaceUsable: project.workspaceUsable,
    defaultAgentId: project.defaultAgentId,
    goalSummary: project.goalSummary,
    createdAt: project.createdAt,
    updatedAt: project.updatedAt,
  };
}

export function encodeProjects(projects: readonly Project[]): Project[] {
  return projects.map(encodeProject);
}

function decodeProject(raw: unknown): Project | null {
  if (!isRecord(raw) || typeof raw.id !== 'string' || raw.id === '' || typeof raw.name !== 'string') {
    return null;
  }
  const project: Project = {
    id: raw.id,
    name: raw.name,
    description: typeof raw.description === 'string' ? raw.description : '',
    color: typeof raw.color === 'string' ? raw.color : '',
    sortOrder: typeof raw.sortOrder === 'number' && Number.isFinite(raw.sortOrder) ? raw.sortOrder : 0,
    goalSummary: typeof raw.goalSummary === 'string' ? raw.goalSummary : '',
    createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : null,
    updatedAt: typeof raw.updatedAt === 'string' ? raw.updatedAt : null,
  };
  if (typeof raw.workspacePath === 'string') {
    project.workspacePath = raw.workspacePath;
  }
  if (typeof raw.workspaceUsable === 'boolean') {
    project.workspaceUsable = raw.workspaceUsable;
  }
  if (typeof raw.defaultAgentId === 'string' || raw.defaultAgentId === null) {
    project.defaultAgentId = raw.defaultAgentId;
  }
  return project;
}

export function decodeProjects(raw: unknown): Project[] | null {
  if (!Array.isArray(raw)) {
    return null;
  }
  return raw.map(decodeProject).filter((project): project is Project => project !== null);
}
