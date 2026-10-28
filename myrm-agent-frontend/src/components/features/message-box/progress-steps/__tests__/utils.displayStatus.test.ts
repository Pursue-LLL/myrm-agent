import { describe, expect, it } from 'vitest';

import { getDisplayStatus, getStatusLabelKey } from '../utils';

describe('getDisplayStatus', () => {
  it.each(['user_declined', 'approval_timeout'])('shows a refused call (%s) as a warning', (error_category) => {
    expect(getDisplayStatus({ status: 'error', error_category })).toBe('warning');
  });

  it.each(['policy_denied', 'guardrail_blocked', 'execution_failure', undefined])(
    'keeps %s as an error',
    (error_category) => {
      expect(getDisplayStatus({ status: 'error', error_category })).toBe('error');
    },
  );

  it('never changes a step that is not an error', () => {
    expect(getDisplayStatus({ status: 'success', error_category: 'user_declined' })).toBe('success');
    expect(getDisplayStatus({ status: 'blocked', error_category: 'approval_timeout' })).toBe('blocked');
    expect(getDisplayStatus({ status: undefined, error_category: 'user_declined' })).toBeUndefined();
  });
});

describe('getStatusLabelKey', () => {
  it.each(['user_declined', 'approval_timeout'])('names a refused call (%s) by what happened', (error_category) => {
    expect(getStatusLabelKey({ status: 'error', error_category })).toBe(`errorCategories.${error_category}`);
  });

  it.each(['policy_denied', 'execution_failure', undefined])('names %s as a failure', (error_category) => {
    expect(getStatusLabelKey({ status: 'error', error_category })).toBe('statusLabels.error');
  });

  it.each(['success', 'warning', 'cancelled', 'complete', 'blocked'] as const)(
    'names a %s step by its status',
    (status) => {
      expect(getStatusLabelKey({ status })).toBe(`statusLabels.${status}`);
    },
  );

  it('never renames a step that is not an error, whatever its category says', () => {
    expect(getStatusLabelKey({ status: 'success', error_category: 'user_declined' })).toBe('statusLabels.success');
  });

  it('has no word for a step without a status', () => {
    expect(getStatusLabelKey({ status: undefined })).toBeNull();
    expect(getStatusLabelKey({ status: undefined, error_category: 'user_declined' })).toBeNull();
  });
});
