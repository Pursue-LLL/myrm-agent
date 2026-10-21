/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => false,
}));

import { ShareConversationDialog } from '../ShareConversationDialog';

function renderDialog(props: Partial<React.ComponentProps<typeof ShareConversationDialog>> = {}) {
  const onOpenChange = vi.fn();
  const onCreateLink = vi.fn();
  const onRevoke = vi.fn();
  const result = render(
    <ShareConversationDialog
      open
      onOpenChange={onOpenChange}
      shareUrl={null}
      expiresAt={null}
      revoked={false}
      passwordProtected={false}
      loading={false}
      onCreateLink={onCreateLink}
      onRevoke={onRevoke}
      {...props}
    />,
  );
  return { onOpenChange, onCreateLink, onRevoke, ...result };
}

describe('ShareConversationDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the create form (password + TTL) when unshared', () => {
    renderDialog();

    expect(screen.getByText('chat.share.title')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('chat.share.passwordPlaceholder')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.share.createLink' })).toBeEnabled();
  });

  it('shows a loading indicator while the status query runs', () => {
    renderDialog({ loading: true });

    expect(screen.getByText('chat.share.loading')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('chat.share.passwordPlaceholder')).not.toBeInTheDocument();
  });

  it('renders an active unprotected link with copy and revoke actions', () => {
    renderDialog({
      shareUrl: 'https://share.example.com/api/v1/public/chat-share/abc',
      expiresAt: 1_800_000_000,
    });

    expect(screen.getByDisplayValue('https://share.example.com/api/v1/public/chat-share/abc')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.share.copyLink' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'chat.share.revoke' })).toBeEnabled();
    expect(screen.queryByPlaceholderText('chat.share.passwordPlaceholder')).not.toBeInTheDocument();
  });

  it('renders a password-protected status with revoke action', () => {
    renderDialog({ passwordProtected: true });

    expect(screen.getByText('chat.share.passwordProtectedStatus')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.share.revoke' })).toBeEnabled();
    expect(screen.queryByPlaceholderText('chat.share.passwordPlaceholder')).not.toBeInTheDocument();
  });

  it('shows the revoked notice together with a re-create form', () => {
    renderDialog({ revoked: true });

    expect(screen.getByText('chat.share.revokedStatus')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('chat.share.passwordPlaceholder')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.share.createLink' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'chat.share.revoke' })).not.toBeInTheDocument();
  });

  it('creates a link with the selected TTL and password', () => {
    const { onCreateLink } = renderDialog();

    fireEvent.change(screen.getByPlaceholderText('chat.share.passwordPlaceholder'), {
      target: { value: 's3cret' },
    });
    const ttlButtons = screen.getAllByRole('button', { name: 'chat.share.ttlDays' });
    fireEvent.click(ttlButtons[1]);

    fireEvent.click(screen.getByRole('button', { name: 'chat.share.createLink' }));

    expect(onCreateLink).toHaveBeenCalledWith(7, 's3cret');
  });

  it('revokes via the footer action', () => {
    const { onRevoke } = renderDialog({
      shareUrl: 'https://share.example.com/api/v1/public/chat-share/abc',
    });

    fireEvent.click(screen.getByRole('button', { name: 'chat.share.revoke' }));

    expect(onRevoke).toHaveBeenCalledTimes(1);
  });
});
