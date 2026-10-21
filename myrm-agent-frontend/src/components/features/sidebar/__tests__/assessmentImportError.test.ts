import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api';

import { resolveAssessmentImportErrorMessage, resolveAssessmentImportFailureReason } from '../assessmentImportError';

const t = (key: string): string => key;

describe('resolveAssessmentImportErrorMessage', () => {
  it('returns generic fallback for non-ApiError', () => {
    expect(resolveAssessmentImportErrorMessage(new Error('boom'), t)).toBe('milestone.importFailed');
  });

  it('maps structured duplicate reason', () => {
    const error = new ApiError('ignored', 409, [
      { field: 'import_reason', issue: 'artifact_version_already_imported' },
    ]);
    expect(resolveAssessmentImportErrorMessage(error, t)).toBe('milestone.importDuplicate');
  });

  it('maps structured non-actionable reason', () => {
    const error = new ApiError('ignored', 422, [{ field: 'import_reason', issue: 'no_actionable_tasks' }]);
    expect(resolveAssessmentImportErrorMessage(error, t)).toBe('milestone.importNoActionable');
  });

  it('maps structured no-task reason', () => {
    const error = new ApiError('ignored', 422, [{ field: 'import_reason', issue: 'no_importable_tasks' }]);
    expect(resolveAssessmentImportErrorMessage(error, t)).toBe('milestone.importNoTasks');
  });

  it('maps structured artifact-not-found reason', () => {
    const error = new ApiError('ignored', 404, [{ field: 'import_reason', issue: 'artifact_not_found' }]);
    expect(resolveAssessmentImportErrorMessage(error, t)).toBe('milestone.importArtifactNotFound');
  });

  it('maps structured project-not-found reason', () => {
    const error = new ApiError('ignored', 404, [{ field: 'import_reason', issue: 'project_not_found' }]);
    expect(resolveAssessmentImportErrorMessage(error, t)).toBe('milestone.importProjectNotFound');
  });

  it('falls back to message matching when structured reason is absent', () => {
    const error = new ApiError('Artifact version already imported for this project');
    expect(resolveAssessmentImportErrorMessage(error, t)).toBe('milestone.importDuplicate');
  });

  it('returns machine-readable failure reason for structured errors', () => {
    const error = new ApiError('ignored', 404, [{ field: 'import_reason', issue: 'project_not_found' }]);
    expect(resolveAssessmentImportFailureReason(error)).toBe('project_not_found');
  });

  it('falls back to unknown failure reason for non-api errors', () => {
    expect(resolveAssessmentImportFailureReason(new Error('boom'))).toBe('unknown_error');
  });
});
