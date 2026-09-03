import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ObsidianVaultBindingSection } from '../ObsidianVaultBindingSection';
import { wikiService } from '@/services/wikiService';

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getObsidianVaultBinding: vi.fn(),
    bindObsidianVault: vi.fn(),
    unbindObsidianVault: vi.fn(),
    syncObsidianVaultDelta: vi.fn(),
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
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
  });

  it('renders unbound state when no vault is bound', async () => {
    vi.mocked(wikiService.getObsidianVaultBinding).mockResolvedValue({
      is_bound: false,
      vault_path: '',
      is_active: false,
      last_sync_watermark: 0,
      auto_sync_on_recall: true,
      allow_inbox_write: true,
      inbox_folder_name: '_Myrm_Inbox',
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
      auto_sync_on_recall: true,
      allow_inbox_write: true,
      inbox_folder_name: '_Myrm_Inbox',
      updated_at: 1700000000,
    });

    render(<ObsidianVaultBindingSection />);

    await waitFor(() => {
      expect(screen.getByText('/Users/test/Vault')).toBeDefined();
      expect(screen.getByText('syncDelta')).toBeDefined();
    });
  });
});
