/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import type { DiscoverySearchResult } from '@/services/skill';

import { SkillUninstallDialogs, useSkillUninstall } from '../SkillUninstallFlow';

const toastMock = vi.hoisted(() => vi.fn());
const uninstallMock = vi.hoisted(() => vi.fn());

const TEXTS: Record<string, string> = {
  uninstall: 'Uninstall',
  uninstallConfirm: 'Remove this skill?',
  uninstalled: 'Uninstalled',
  uninstallFailed: 'Uninstall failed',
  scanCancel: 'Cancel',
  forceUninstallTitle: 'Force uninstall?',
  forceUninstallDesc: '{name} is used by {count} other skill(s).',
  forceUninstall: 'Force Uninstall',
};

const stableT = (key: string, values?: Record<string, string>): string =>
  (TEXTS[key] ?? key).replace(/\{(\w+)\}/g, (_, name: string) => values?.[name] ?? `{${name}}`);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: toastMock,
}));

const SKILL = { name: 'GitHub Helper', installed_skill_id: 'local::github-helper' } as DiscoverySearchResult;

function Harness({ skill = SKILL, onInstalled }: { skill?: DiscoverySearchResult; onInstalled?: () => void }) {
  const { requestUninstall, dialogProps } = useSkillUninstall({ uninstall: uninstallMock, onInstalled });
  return (
    <>
      <button type="button" onClick={() => requestUninstall(skill)}>
        open
      </button>
      <SkillUninstallDialogs {...dialogProps} />
    </>
  );
}

function conflict(dependents: string[]) {
  const error = new ApiError('Skill is referenced', 409, [], undefined, 'DEPENDENTS_EXIST');
  error.data = { code: 'DEPENDENTS_EXIST', impacted_dependents: dependents };
  return error;
}

const openAndConfirm = () => {
  fireEvent.click(screen.getByText('open'));
  fireEvent.click(screen.getByRole('button', { name: /^Uninstall$/ }));
};

describe('useSkillUninstall and SkillUninstallDialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    uninstallMock.mockReset();
  });

  it('asks for confirmation with the skill name and a destructive-text icon', () => {
    render(<Harness />);
    expect(screen.queryByText('Remove this skill?', { exact: false })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('open'));

    expect(screen.getByText('Remove this skill?', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('GitHub Helper')).toBeInTheDocument();
    expect(document.querySelector('svg.lucide-trash-2.text-destructive-text')).not.toBeNull();
  });

  it('does not uninstall when the confirmation is cancelled', async () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('open'));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByText('Remove this skill?', { exact: false })).not.toBeInTheDocument());
    expect(uninstallMock).not.toHaveBeenCalled();
  });

  it('uninstalls by the canonical installed skill id and reports success', async () => {
    uninstallMock.mockResolvedValue(true);
    const onInstalled = vi.fn();
    render(<Harness onInstalled={onInstalled} />);

    openAndConfirm();

    await waitFor(() => expect(uninstallMock).toHaveBeenCalledWith('local::github-helper'));
    expect(toastMock).toHaveBeenCalledWith({ title: 'Uninstalled GitHub Helper' });
    expect(onInstalled).toHaveBeenCalledTimes(1);
  });

  it('reports a refused uninstall without refreshing the list', async () => {
    uninstallMock.mockResolvedValue(false);
    const onInstalled = vi.fn();
    render(<Harness onInstalled={onInstalled} />);

    openAndConfirm();

    await waitFor(() => expect(toastMock).toHaveBeenCalledWith({ title: 'Uninstall failed', variant: 'destructive' }));
    expect(onInstalled).not.toHaveBeenCalled();
  });

  it('fails fast when the result has no installed skill id', async () => {
    render(<Harness skill={{ ...SKILL, installed_skill_id: null }} />);

    openAndConfirm();

    await waitFor(() => expect(toastMock).toHaveBeenCalledWith({ title: 'Uninstall failed', variant: 'destructive' }));
    expect(uninstallMock).not.toHaveBeenCalled();
  });

  it('surfaces the error message of an unexpected failure', async () => {
    uninstallMock.mockRejectedValue(new Error('disk is read-only'));
    render(<Harness />);

    openAndConfirm();

    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith({
        title: 'Uninstall failed',
        description: 'disk is read-only',
        variant: 'destructive',
      }),
    );
  });

  it('lists the dependents on a conflict and does nothing when the force prompt is dismissed', async () => {
    uninstallMock.mockRejectedValue(conflict(['dep-a', 'dep-b']));
    render(<Harness />);

    openAndConfirm();

    expect(await screen.findByText('Force uninstall?')).toBeInTheDocument();
    expect(screen.getByText('GitHub Helper is used by 2 other skill(s).')).toBeInTheDocument();
    expect(screen.getByText('dep-a')).toBeInTheDocument();
    expect(screen.getByText('dep-b')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByText('Force uninstall?')).not.toBeInTheDocument());
    expect(uninstallMock).toHaveBeenCalledTimes(1);
  });

  it('force-uninstalls after a conflict and reports the result', async () => {
    uninstallMock.mockRejectedValueOnce(conflict([])).mockResolvedValueOnce(true);
    const onInstalled = vi.fn();
    render(<Harness onInstalled={onInstalled} />);

    openAndConfirm();
    fireEvent.click(await screen.findByRole('button', { name: /Force Uninstall/ }));

    await waitFor(() => expect(uninstallMock).toHaveBeenLastCalledWith('local::github-helper', true));
    expect(toastMock).toHaveBeenCalledWith({ title: 'Uninstalled GitHub Helper' });
    expect(onInstalled).toHaveBeenCalledTimes(1);
  });

  it('reports a failed force uninstall', async () => {
    uninstallMock.mockRejectedValueOnce(conflict(['dep-a'])).mockRejectedValueOnce(new Error('still in use'));
    render(<Harness />);

    openAndConfirm();
    fireEvent.click(await screen.findByRole('button', { name: /Force Uninstall/ }));

    await waitFor(() => expect(toastMock).toHaveBeenCalledWith({ title: 'Uninstall failed', variant: 'destructive' }));
  });
});
