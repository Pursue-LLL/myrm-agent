/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { CredentialsDialogs } from '../CredentialsDialogs';
import { SUPPORTED_INTEGRATIONS, type OauthIntegration } from '../credentialsConstants';

const stableT = (key: string, values?: Record<string, string>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));
vi.mock('@/components/features/app-shell/confirm-dialog', () => ({ ConfirmDialog: () => null }));

function registeredIntegration(id: string): OauthIntegration {
  const integration = SUPPORTED_INTEGRATIONS.find((candidate) => candidate.id === id);
  if (!integration) {
    throw new Error(`The ${id} integration is not registered`);
  }
  return integration;
}

const XAI = registeredIntegration('xai');

type Props = ComponentProps<typeof CredentialsDialogs>;

function buildProps(overrides: Partial<Props> = {}): Props {
  return {
    clearSyncedMemory: false,
    closeConnectModal: vi.fn(),
    connectModalTarget: XAI,
    deleteTarget: null,
    deleteVaultTarget: null,
    disconnectConfirmTarget: null,
    editingVaultCred: null,
    googleOauthConfigured: null,
    googleOauthPolling: false,
    handleConnectOauth: vi.fn(),
    handleDeleteConfirm: vi.fn(),
    handleDeleteVaultConfirm: vi.fn(),
    handleDisconnectOauth: vi.fn(),
    handleGoogleWorkspaceConnect: vi.fn(),
    handleSaveVaultCredential: vi.fn(),
    handleXaiOAuthConnect: vi.fn(),
    providerTreeCount: 0,
    scopeInput: '',
    setClearSyncedMemory: vi.fn(),
    setDeleteTarget: vi.fn(),
    setDeleteVaultTarget: vi.fn(),
    setDisconnectConfirmTarget: vi.fn(),
    setScopeInput: vi.fn(),
    setTokenInput: vi.fn(),
    setUserIdInput: vi.fn(),
    setVaultDesc: vi.fn(),
    setVaultLabel: vi.fn(),
    setVaultModalOpen: vi.fn(),
    setVaultPassword: vi.fn(),
    setVaultTotp: vi.fn(),
    tokenInput: '',
    userIdInput: '',
    vaultDesc: '',
    vaultLabel: '',
    vaultModalOpen: false,
    vaultPassword: '',
    vaultTotp: '',
    xaiOauthPolling: false,
    xaiUserCode: '',
    xaiVerificationUrl: '',
    ...overrides,
  };
}

describe('CredentialsDialogs: xAI device-code login', () => {
  it('offers the authorization and starts it on click', () => {
    const handleXaiOAuthConnect = vi.fn();
    render(<CredentialsDialogs {...buildProps({ handleXaiOAuthConnect })} />);

    expect(screen.getByText('xaiOauthConnectDesc')).toBeInTheDocument();
    expect(screen.queryByText('xaiOauthCodeHint')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'xaiOauthConnectBtn' }));

    expect(handleXaiOAuthConnect).toHaveBeenCalledOnce();
  });

  it('shows the code and a way back to the authorization page while waiting', () => {
    render(
      <CredentialsDialogs
        {...buildProps({
          xaiOauthPolling: true,
          xaiUserCode: 'ABCD-1234',
          xaiVerificationUrl: 'https://x.ai/device?code=ABCD-1234',
        })}
      />,
    );

    expect(screen.getByText('xaiOauthCode')).toBeInTheDocument();
    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
    expect(screen.getByText('xaiOauthCodeHint')).toBeInTheDocument();
    const reopen = screen.getByRole('link', { name: 'xaiOauthReopen' });
    expect(reopen).toHaveAttribute('href', 'https://x.ai/device?code=ABCD-1234');
    expect(reopen).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByRole('button', { name: 'xaiOauthWaiting' })).toBeDisabled();
  });

  it('only disables the button while the code is still being requested', () => {
    render(<CredentialsDialogs {...buildProps({ xaiOauthPolling: true })} />);

    expect(screen.getByRole('button', { name: 'xaiOauthWaiting' })).toBeDisabled();
    expect(screen.queryByText('xaiOauthCode')).not.toBeInTheDocument();
  });
});
