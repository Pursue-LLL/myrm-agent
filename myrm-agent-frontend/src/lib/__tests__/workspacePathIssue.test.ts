import { describe, expect, it } from 'vitest';
import { ApiError } from '@/lib/api';
import { workspacePathIssueMessageKey } from '../workspacePathIssue';

const refused = (field: string, issue: string) => new ApiError('refused', 40001, [{ field, issue }]);

describe('workspacePathIssueMessageKey', () => {
  it('maps a too-broad folder on either workspace field', () => {
    expect(workspacePathIssueMessageKey(refused('workspace_dir', 'too_broad'))).toBe('tooBroad');
    expect(workspacePathIssueMessageKey(refused('workspace_path', 'too_broad'))).toBe('tooBroad');
  });

  it('maps a protected folder', () => {
    expect(workspacePathIssueMessageKey(refused('workspace_dir', 'dangerous'))).toBe('dangerous');
  });

  it('leaves other refusals to the caller generic message', () => {
    expect(workspacePathIssueMessageKey(refused('workspace_dir', 'not_a_directory'))).toBeNull();
    expect(workspacePathIssueMessageKey(refused('workspace_dir', 'not_absolute'))).toBeNull();
  });

  it('ignores an issue reported for another field', () => {
    expect(workspacePathIssueMessageKey(refused('color', 'too_broad'))).toBeNull();
  });

  it('ignores errors that are not API errors or carry no details', () => {
    expect(workspacePathIssueMessageKey(new Error('too_broad'))).toBeNull();
    expect(workspacePathIssueMessageKey(new ApiError('plain'))).toBeNull();
    expect(workspacePathIssueMessageKey(undefined)).toBeNull();
  });

  it('finds the workspace refusal among several details', () => {
    const error = new ApiError('refused', 40001, [
      { field: 'name', issue: 'required' },
      { field: 'workspace_path', issue: 'too_broad' },
    ]);
    expect(workspacePathIssueMessageKey(error)).toBe('tooBroad');
  });
});
