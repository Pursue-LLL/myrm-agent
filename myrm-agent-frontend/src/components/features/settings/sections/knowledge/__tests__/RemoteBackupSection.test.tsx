/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({ get: () => undefined, set: vi.fn() }),
}));

import RemoteBackupSection from '../RemoteBackupSection';

describe('RemoteBackupSection', () => {
  it('says up front, before backups are switched on, that what gets uploaded is not encrypted', () => {
    render(<RemoteBackupSection />);

    expect(screen.getByText('notePlain')).toBeInTheDocument();
    expect(screen.getByRole('switch')).not.toBeChecked();
  });
});
