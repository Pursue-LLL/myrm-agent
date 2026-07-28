import { describe, expect, it } from 'vitest';

import { resolveTopicWorkspaceDisplayLabel } from '../topicWorkspaceLabel';

describe('resolveTopicWorkspaceDisplayLabel', () => {
  const projects = [
    {
      id: 'proj-1',
      name: 'Weekly Reports',
      description: '',
      color: '#000',
      sortOrder: 0,
      workspacePath: '/Users/me/vault',
      goalSummary: '',
      createdAt: null,
      updatedAt: null,
    },
  ];

  it('returns project name and workspace path', () => {
    expect(
      resolveTopicWorkspaceDisplayLabel(
        { projectId: 'proj-1', authorizedPath: null, workspaceLabel: 'project:proj-1' },
        projects,
      ),
    ).toBe('Weekly Reports · /Users/me/vault');
  });

  it('returns authorized path for IM-only bindings', () => {
    expect(
      resolveTopicWorkspaceDisplayLabel(
        { projectId: null, authorizedPath: '/tmp/vault', workspaceLabel: '/tmp/vault' },
        projects,
      ),
    ).toBe('/tmp/vault');
  });

  it('returns null when no workspace is bound', () => {
    expect(
      resolveTopicWorkspaceDisplayLabel(
        { projectId: null, authorizedPath: null, workspaceLabel: null },
        projects,
      ),
    ).toBeNull();
  });
});
