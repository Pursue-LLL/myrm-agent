/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

import { RemoteBackupStatus } from '../RemoteBackupStatus';
import type { AutoSyncStatus } from '../remoteBackupApi';

const NEVER: AutoSyncStatus = {
  last_success_at: null,
  last_attempt_at: null,
  last_error_code: null,
  consecutive_failures: 0,
};
const FAILING: AutoSyncStatus = {
  last_success_at: '2026-10-20T12:00:00Z',
  last_attempt_at: '2026-10-26T12:00:00Z',
  last_error_code: 'upload',
  consecutive_failures: 3,
};

describe('RemoteBackupStatus', () => {
  it('shows nothing while the server has not answered', () => {
    const { container } = render(<RemoteBackupStatus status={null} autoSync />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the last backup that completed', () => {
    render(<RemoteBackupStatus status={{ ...NEVER, last_success_at: '2026-10-26T12:00:00Z' }} autoSync />);

    expect(screen.getByText('statusLastBackup')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('says why the schedule is failing in localized words, and still names the last good backup', () => {
    render(<RemoteBackupStatus status={FAILING} autoSync />);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('statusFailing');
    expect(alert).toHaveTextContent('errorCodes.upload');
    expect(screen.getByText('statusLastBackup')).toBeInTheDocument();
  });

  it('reads a reason it does not know as an internal error', () => {
    render(<RemoteBackupStatus status={{ ...FAILING, last_error_code: 'somethingNew' }} autoSync />);

    expect(screen.getByRole('alert')).toHaveTextContent('errorCodes.internal');
  });

  it('keeps a failing schedule out of sight once the schedule is off', () => {
    render(<RemoteBackupStatus status={FAILING} autoSync={false} />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('statusLastBackup')).toBeInTheDocument();
  });

  it('says no backup has completed yet when the schedule is on and none has', () => {
    render(<RemoteBackupStatus status={NEVER} autoSync />);

    expect(screen.getByText('statusNone')).toBeInTheDocument();
  });

  it('stays quiet when the schedule is off and nothing has been backed up', () => {
    const { container } = render(<RemoteBackupStatus status={NEVER} autoSync={false} />);

    expect(container).not.toHaveTextContent('statusNone');
  });
});
