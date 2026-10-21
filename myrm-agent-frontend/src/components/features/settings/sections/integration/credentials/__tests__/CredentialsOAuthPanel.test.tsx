/** @vitest-environment jsdom */
import { render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { CredentialsOAuthPanel } from '../CredentialsOAuthPanel';
import type { OauthCredentialRecord } from '../credentialsConstants';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const NOW_S = Date.now() / 1000;
const HOUR_S = 3600;
const DAY_S = 86_400;

type Props = ComponentProps<typeof CredentialsOAuthPanel>;

function renderPanel(oauthCreds: OauthCredentialRecord[]) {
  const props: Props = {
    googleOauthPolling: false,
    googleWorkspaceWriteEnabled: false,
    handleGoogleWorkspaceConnect: vi.fn(),
    isOauthLoading: false,
    oauthCreds,
    openConnectModal: vi.fn(),
    prepareDisconnect: vi.fn(),
  };
  return render(<CredentialsOAuthPanel {...props} />);
}

function cardOf(name: string): HTMLElement {
  const card = screen.getByText(name).closest<HTMLElement>('.rounded-xl');
  if (!card) {
    throw new Error(`No card rendered for ${name}`);
  }
  return card;
}

describe('CredentialsOAuthPanel connection health', () => {
  it('shows a renewable credential as connected even when its access token lapsed, without an expiry row', () => {
    renderPanel([
      {
        issuer: 'xai',
        connected: true,
        renewable: true,
        user_id: 'grok-user',
        expires_at: NOW_S - 7 * HOUR_S,
      },
    ]);

    const card = within(cardOf('xAI / SuperGrok'));

    expect(card.getByText('connected')).toBeTruthy();
    expect(card.queryByText('expired')).toBeNull();
    expect(card.getByText('grok-user')).toBeTruthy();
    expect(card.queryByText('expiresAt:')).toBeNull();
  });

  it('hides the details box of a renewable credential that has nothing else to show', () => {
    renderPanel([{ issuer: 'xai', connected: true, renewable: true, expires_at: NOW_S + 6 * HOUR_S }]);

    const card = within(cardOf('xAI / SuperGrok'));

    expect(card.getByText('connected')).toBeTruthy();
    expect(card.queryByText('expiresAt:')).toBeNull();
    expect(card.queryByText('userId:')).toBeNull();
  });

  it('keeps the expiry warning and row for a credential that cannot renew itself', () => {
    renderPanel([{ issuer: 'feishu', connected: true, expires_at: NOW_S + 3 * DAY_S }]);

    const card = within(cardOf('Feishu / 飞书'));

    expect(card.getByText('expiringSoon:{"days":3}')).toBeTruthy();
    expect(card.getByText('expiresAt:')).toBeTruthy();
  });

  it('offers re-authorization when the provider rejected the refresh token', () => {
    renderPanel([
      {
        issuer: 'google_workspace',
        connected: true,
        renewable: true,
        needs_reauth: true,
        expires_at: NOW_S + 6 * HOUR_S,
      },
    ]);

    const card = within(cardOf('Google Workspace'));

    expect(card.getByText('expired')).toBeTruthy();
    expect(card.getByText('Fix Now')).toBeTruthy();
    expect(card.queryByText('connected')).toBeNull();
  });
});
