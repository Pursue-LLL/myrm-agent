// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn() }));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/lib/api', () => ({
  apiRequest,
  getApiUrl: (endpoint: string) => `http://api.test/api/v1${endpoint}`,
}));

import VaultArtifactCard, { getVaultDownloadUrl, getVaultMeta } from '../VaultArtifactCard';

const META = {
  id: 'obj-1',
  filename: 'report.csv',
  content_type: 'text/csv',
  size_bytes: 2048,
  created_at: 1,
};

describe('vault object URLs', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('names the owning chat in the meta request when one is known', async () => {
    apiRequest.mockResolvedValue(META);
    await getVaultMeta('obj-1', 'chat 1');
    expect(apiRequest).toHaveBeenCalledWith('/files/vault/obj-1/meta?chat_id=chat%201', { method: 'GET' });
  });

  it('leaves the meta request bare without a chat', async () => {
    apiRequest.mockResolvedValue(META);
    await getVaultMeta('obj-1');
    expect(apiRequest).toHaveBeenCalledWith('/files/vault/obj-1/meta', { method: 'GET' });
  });

  it('builds the download URL on the files route with the chat id', () => {
    expect(getVaultDownloadUrl('obj-1', 'chat-1')).toBe(
      'http://api.test/api/v1/files/vault/obj-1/content?download=1&chat_id=chat-1',
    );
    expect(getVaultDownloadUrl('obj-1')).toBe('http://api.test/api/v1/files/vault/obj-1/content?download=1');
  });
});

describe('VaultArtifactCard', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('downloads through the chat-scoped URL and hides the raw pointer', async () => {
    apiRequest.mockResolvedValue(META);
    const created: HTMLAnchorElement[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      created.push(this);
    });

    const { container } = render(<VaultArtifactCard id="obj-1" chatId="chat-1" />);
    fireEvent.click(await screen.findByRole('button', { name: 'downloadFull' }));

    expect(created[0]?.href).toBe('http://api.test/api/v1/files/vault/obj-1/content?download=1&chat_id=chat-1');
    expect(created[0]?.getAttribute('download')).toBe('report.csv');
    expect(container.textContent).not.toContain('vault://');
    click.mockRestore();
  });

  it('shows the friendly failure copy when the file cannot be loaded', async () => {
    apiRequest.mockRejectedValue(new Error('boom'));
    const { container } = render(<VaultArtifactCard id="obj-1" chatId="chat-1" />);
    expect(await screen.findByText(/unavailable/)).toBeTruthy();
    expect(container.textContent).not.toContain('vault://');
  });
});
