import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ObsidianVaultBindingSection } from '../ObsidianVaultBindingSection';
import { wikiService } from '@/services/wikiService';
import { isLocalMode } from '@/lib/deploy-mode';

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getObsidianVaultBinding: vi.fn(),
    bindObsidianVault: vi.fn(),
    unbindObsidianVault: vi.fn(),
    syncObsidianVaultDelta: vi.fn(),
  },
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: vi.fn(() => true),
}));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('ObsidianVaultBindingSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(isLocalMode).mockReturnValue(true);
  });

  it('renders unbound state when no vault is bound', async () => {
    vi.mocked(wikiService.getObsidianVaultBinding).mockResolvedValue({
      is_bound: false,
      vault_path: '',
      is_active: false,
      last_sync_watermark: 0,
      updated_at: 0,
    });

    render(<ObsidianVaultBindingSection />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('pathPlaceholder')).toBeDefined();
    });
    expect(screen.getByText('bindButton')).toBeDefined();
  });

  it('renders bound state when vault is bound', async () => {
    vi.mocked(wikiService.getObsidianVaultBinding).mockResolvedValue({
      is_bound: true,
      vault_path: '/Users/test/Vault',
      is_active: true,
      last_sync_watermark: 1700000000,
      updated_at: 1700000000,
    });

    render(<ObsidianVaultBindingSection />);

    await waitFor(() => {
      expect(screen.getByText('/Users/test/Vault')).toBeDefined();
      expect(screen.getByText('syncDelta')).toBeDefined();
    });
  });

  it('hides the local path binding in sandbox deployments', async () => {
    vi.mocked(isLocalMode).mockReturnValue(false);

    render(<ObsidianVaultBindingSection />);

    await waitFor(() => {
      expect(screen.getByText('cloudHint')).toBeDefined();
    });
    expect(screen.queryByPlaceholderText('pathPlaceholder')).toBeNull();
    expect(wikiService.getObsidianVaultBinding).not.toHaveBeenCalled();
  });
});
