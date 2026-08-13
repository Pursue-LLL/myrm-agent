/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}));

vi.mock('@/hooks/settings/useSettingsSubTabUrl', () => ({
  useSettingsSubTabUrl: () => ({ handleTabChange: vi.fn() }),
  defaultSubTabResolver: () => () => 'memory',
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => false,
  getApiBaseUrl: () => 'http://localhost:8080/api/v1',
  getBackendBaseUrl: () => 'http://localhost:8080',
  resolveE2eApiBase: () => '',
  shouldRedirectToLoginOnAuthFailure: () => true,
}));

vi.mock('../sections/knowledge/MemorySection', () => ({
  default: () => <div data-testid="memory-section" />,
}));
vi.mock('../sections/knowledge/MemoryBackupSection', () => ({
  default: () => <div data-testid="memory-backup-section" />,
}));
vi.mock('../sections/knowledge/RemoteBackupSection', () => ({
  default: () => <div data-testid="remote-backup-section" />,
}));
vi.mock('../sections/knowledge/MigrationWizardSection', () => ({
  default: () => <div data-testid="migration-wizard-section" />,
}));

import MemoryCenterSection from '../sections/knowledge/MemoryCenterSection';

describe('MemoryCenterSection', () => {
  beforeEach(() => {
    searchParams.delete('sub');
  });

  it('mounts memory tab shell', () => {
    render(<MemoryCenterSection />);
    expect(screen.getByTestId('memory-section')).toBeInTheDocument();
  });
});
