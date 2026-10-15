import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProviderConfig } from '@/store/config/providerTypes';

const { mockFetchStatus } = vi.hoisted(() => ({ mockFetchStatus: vi.fn() }));

vi.mock('@/services/provider-oauth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/provider-oauth')>()),
  fetchProviderOAuthStatus: mockFetchStatus,
}));

import { reconcileProviderOAuthFlags } from '../provider-oauth-reconcile';

function provider(id: string, oauthConnected?: boolean): ProviderConfig {
  return {
    id,
    routingProfile: id,
    name: id,
    isBuiltIn: true,
    isEnabled: true,
    apiKeys: [],
    apiUrl: '',
    enabledModels: [],
    availableModels: [],
    oauthConnected,
  };
}

describe('reconcileProviderOAuthFlags', () => {
  const applyFlag = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('clears a stored connected flag the server no longer backs', async () => {
    mockFetchStatus.mockResolvedValue({ provider: 'xai', issuer: 'xai', connected: false });
    const providers = [provider('xai', true)];

    await reconcileProviderOAuthFlags(providers, applyFlag);

    expect(mockFetchStatus).toHaveBeenCalledWith('xai');
    expect(applyFlag).toHaveBeenCalledExactlyOnceWith('xai', { oauthConnected: false });
  });

  it('records a login the stored flag does not know about', async () => {
    mockFetchStatus.mockResolvedValue({ provider: 'xai', issuer: 'xai', connected: true });
    const providers = [provider('xai', false)];

    await reconcileProviderOAuthFlags(providers, applyFlag);

    expect(applyFlag).toHaveBeenCalledExactlyOnceWith('xai', { oauthConnected: true });
  });

  it.each([
    ['connected on both sides', true, true],
    ['disconnected on both sides', false, false],
    ['an absent flag and a disconnected server', undefined, false],
  ])('changes nothing for %s', async (_label, stored, serverConnected) => {
    mockFetchStatus.mockResolvedValue({ provider: 'xai', issuer: 'xai', connected: serverConnected });
    const providers = [provider('xai', stored)];

    await reconcileProviderOAuthFlags(providers, applyFlag);

    expect(applyFlag).not.toHaveBeenCalled();
  });

  it('treats a status without a usable connected field as disconnected', async () => {
    mockFetchStatus.mockResolvedValue({ provider: 'xai', issuer: 'xai' });
    const providers = [provider('xai', true)];

    await reconcileProviderOAuthFlags(providers, applyFlag);

    expect(applyFlag).toHaveBeenCalledExactlyOnceWith('xai', { oauthConnected: false });
  });

  it('only asks about providers that sign in with a subscription', async () => {
    mockFetchStatus.mockResolvedValue({ provider: 'xai', issuer: 'xai', connected: true });
    const providers = [provider('openai', true), provider('xai', true), provider('anthropic')];

    await reconcileProviderOAuthFlags(providers, applyFlag);

    expect(mockFetchStatus).toHaveBeenCalledOnce();
    expect(applyFlag).not.toHaveBeenCalled();
  });

  it('keeps the flag when the status request fails', async () => {
    mockFetchStatus.mockRejectedValue(new Error('network down'));
    const providers = [provider('xai', true)];

    await expect(reconcileProviderOAuthFlags(providers, applyFlag)).resolves.toBeUndefined();

    expect(applyFlag).not.toHaveBeenCalled();
  });

  it('compares the answer with the flag the provider had when the request was sent', async () => {
    const xai = provider('xai', false);
    mockFetchStatus.mockImplementation(async () => {
      xai.oauthConnected = true;
      return { provider: 'xai', issuer: 'xai', connected: false };
    });

    await reconcileProviderOAuthFlags([xai], applyFlag);

    expect(applyFlag).not.toHaveBeenCalled();
  });
});
