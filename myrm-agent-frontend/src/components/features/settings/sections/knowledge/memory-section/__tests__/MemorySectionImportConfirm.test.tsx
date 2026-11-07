import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import {
  actionToastCalls,
  actionToastInfo,
  archive,
  attr,
  click,
  pickImportFile,
  renderSection,
  resetKit,
  storeActions,
  toast,
} from './memorySectionTestKit';
import { confirmOf, fileOf } from './memorySectionFixtures';

beforeEach(resetKit);

describe('MemorySection import: confirming', () => {
  const previewImport = async () => {
    const view = renderSection();
    await pickImportFile(view.container, fileOf('memories.json', '{}'));
    storeActions.fetchMemories.mockClear();
  };

  it('imports, reports the count, closes the review and reloads the list', async () => {
    await previewImport();

    await click(screen.getByRole('button', { name: 'review:confirm' }));

    expect(archive.confirmImportMemories).toHaveBeenCalledExactlyOnceWith('dry-1', true);
    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'importSuccess',
      description: 'importSuccessDesc|{"count":3}',
    });
    expect(attr('import-review', 'data-open')).toBe('false');
    expect(attr('import-review', 'data-source')).toBe('');
    expect(storeActions.fetchMemories).toHaveBeenCalledOnce();
  });

  it('treats a ready readiness report as a plain success', async () => {
    archive.confirmImportMemories.mockResolvedValue(confirmOf({ readiness: { status: 'ready', issues: [] } }));
    await previewImport();

    await click(screen.getByRole('button', { name: 'review:confirm' }));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'importSuccess',
      description: 'importSuccessDesc|{"count":3}',
    });
    expect(actionToastInfo).not.toHaveBeenCalled();
  });

  it('keeps the review open and reports a failed import', async () => {
    archive.confirmImportMemories.mockRejectedValue(new Error('conflict'));
    await previewImport();

    await click(screen.getByRole('button', { name: 'review:confirm' }));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'importFailed',
      description: 'conflict',
      variant: 'destructive',
    });
    expect(attr('import-review', 'data-open')).toBe('true');
    expect(attr('import-review', 'data-importing')).toBe('false');
    expect(storeActions.fetchMemories).not.toHaveBeenCalled();
  });

  it('shows the review as busy while the import runs', async () => {
    const request = deferred<ReturnType<typeof confirmOf>>();
    archive.confirmImportMemories.mockReturnValue(request.promise);
    await previewImport();

    await click(screen.getByRole('button', { name: 'review:confirm' }));
    expect(attr('import-review', 'data-importing')).toBe('true');

    request.resolve(confirmOf());
    await settle();
    expect(attr('import-review', 'data-importing')).toBe('false');
  });

  it('forgets the preview when the review is dismissed', async () => {
    await previewImport();

    await click(screen.getByRole('button', { name: 'review:close' }));
    expect(attr('import-review', 'data-open')).toBe('false');
    expect(attr('import-review', 'data-source')).toBe('');

    await click(screen.getByRole('button', { name: 'review:confirm' }));
    expect(archive.confirmImportMemories).not.toHaveBeenCalled();
  });
});

describe('MemorySection import: post-import readiness', () => {
  const originalLocation = window.location;
  const assign = vi.fn();
  const voiceIssue = { code: 'voice_feature_disabled', severity: 'warning' as const, params: {} };

  beforeEach(() => {
    Object.defineProperty(window, 'location', { value: { ...originalLocation, assign }, writable: true });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', { value: originalLocation, writable: true });
  });

  const confirmWith = async (readiness: NonNullable<ReturnType<typeof confirmOf>['readiness']>) => {
    archive.confirmImportMemories.mockResolvedValue(confirmOf({ readiness }));
    const { container } = renderSection();
    await pickImportFile(container, fileOf('memories.json', '{}'));
    await click(screen.getByRole('button', { name: 'review:confirm' }));
  };

  it('warns with the first issue when it has no settings page', async () => {
    await confirmWith({ status: 'warning', issues: [voiceIssue] });

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'result.readinessStatus.warning',
      description: 'result.readinessIssue.voiceFeatureDisabled',
      variant: 'default',
    });
    expect(actionToastInfo).not.toHaveBeenCalled();
  });

  it('flags a critical report in the destructive style', async () => {
    await confirmWith({ status: 'critical', issues: [{ ...voiceIssue, severity: 'critical' }] });

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'result.readinessStatus.critical',
      description: 'result.readinessIssue.voiceFeatureDisabled',
      variant: 'destructive',
    });
  });

  it('falls back to the summary when the report lists no issue', async () => {
    await confirmWith({ status: 'warning', issues: [] });

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'result.readinessStatus.warning',
      description: 'result.readinessSummary',
      variant: 'default',
    });
  });

  it('offers a shortcut to the settings page that fixes the issue', async () => {
    await confirmWith({ status: 'warning', issues: [{ ...voiceIssue, settings_path: ' /settings?tab=voice ' }] });

    expect(toast).not.toHaveBeenCalled();
    const [title, options] = actionToastCalls()[0];
    expect(title).toBe('result.readinessStatus.warning');
    expect(options).toMatchObject({
      description: 'result.readinessIssue.voiceFeatureDisabled',
      duration: 12000,
      action: { label: 'result.readinessAction.configureVoice' },
    });

    options.action.onClick();
    expect(assign).toHaveBeenCalledExactlyOnceWith('/settings?tab=voice');
  });
});
