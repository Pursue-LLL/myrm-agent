import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { CredentialFile } from '@/services/credentials';

import { CredentialsFilePanel } from '../CredentialsFilePanel';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

const file = (overrides: Partial<CredentialFile> = {}): CredentialFile => ({
  filename: 'google_token.json',
  size: 2048,
  ...overrides,
});

function renderPanel({ credentials = [] as CredentialFile[], isLoading = false } = {}) {
  const setDeleteTarget = vi.fn();
  const view = render(
    <CredentialsFilePanel credentials={credentials} isLoading={isLoading} setDeleteTarget={setDeleteTarget} />,
  );
  return { ...view, setDeleteTarget };
}

describe('CredentialsFilePanel', () => {
  it('lists every stored file with its name and size and counts them in the heading', () => {
    renderPanel({ credentials: [file(), file({ filename: 'aws_credentials', size: 1536 })] });

    expect(screen.getByRole('heading')).toHaveTextContent('Uploaded Credentials');
    expect(screen.getByRole('heading')).toHaveTextContent('2');
    expect(screen.getByText('google_token.json')).toBeInTheDocument();
    expect(screen.getByText('2.00 KB')).toBeInTheDocument();
    expect(screen.getByText('aws_credentials')).toBeInTheDocument();
    expect(screen.getByText('1.50 KB')).toBeInTheDocument();
  });

  it('says so when no file is stored', () => {
    renderPanel();

    expect(screen.getByText('No credentials uploaded yet')).toBeInTheDocument();
  });

  it('shows placeholders instead of the list while loading', () => {
    const { container } = renderPanel({ credentials: [file()], isLoading: true });

    expect(container.querySelectorAll('.animate-pulse')).not.toHaveLength(0);
    expect(screen.queryByText('google_token.json')).toBeNull();
  });

  it('does not claim that no file is stored while still loading', () => {
    renderPanel({ isLoading: true });

    expect(screen.queryByText('No credentials uploaded yet')).toBeNull();
  });

  it.each([
    ['valid', undefined, 'Valid'],
    ['expiring_soon', 5, '5d left'],
    ['expired', undefined, 'Expired'],
  ])('flags a %s file with its own badge', (expiry_status, remaining_days, label) => {
    renderPanel({ credentials: [file({ expiry_status, remaining_days })] });

    expect(screen.getByText(label)).toBeInTheDocument();
    for (const other of ['Valid', '5d left', 'Expired'].filter((text) => text !== label)) {
      expect(screen.queryByText(other)).toBeNull();
    }
  });

  it.each([
    ['no status', undefined],
    ['an unreadable file', 'error'],
    ['an unknown status', 'pending'],
  ])('shows no badge for %s', (_what, expiry_status) => {
    renderPanel({ credentials: [file({ expiry_status })] });

    for (const text of ['Valid', 'Expired']) {
      expect(screen.queryByText(text)).toBeNull();
    }
    expect(screen.queryByText(/d left/)).toBeNull();
  });

  it('asks to delete exactly the file whose button was pressed', async () => {
    const user = userEvent.setup();
    const { setDeleteTarget } = renderPanel({
      credentials: [file(), file({ filename: 'aws_credentials' })],
    });

    await user.click(screen.getByRole('button', { name: 'Delete aws_credentials' }));

    expect(setDeleteTarget).toHaveBeenCalledExactlyOnceWith('aws_credentials');
  });
});
