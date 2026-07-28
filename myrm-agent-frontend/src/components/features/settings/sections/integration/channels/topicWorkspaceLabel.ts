import type { TopicBinding } from '@/services/channels';
import type { Project } from '@/services/projects';

type TopicWorkspaceSource = Pick<
  TopicBinding,
  'projectId' | 'authorizedPath' | 'workspaceLabel'
>;

export function resolveTopicWorkspaceDisplayLabel(
  topic: TopicWorkspaceSource,
  projects: Project[],
): string | null {
  if (topic.projectId) {
    const project = projects.find((item) => item.id === topic.projectId);
    if (project) {
      const path = project.workspacePath?.trim();
      if (path) {
        return `${project.name} · ${path}`;
      }
      return project.name;
    }
    return null;
  }

  if (topic.authorizedPath?.trim()) {
    return topic.authorizedPath.trim();
  }

  const legacyLabel = topic.workspaceLabel?.trim();
  if (legacyLabel && !legacyLabel.startsWith('project:')) {
    return legacyLabel;
  }

  return null;
}
