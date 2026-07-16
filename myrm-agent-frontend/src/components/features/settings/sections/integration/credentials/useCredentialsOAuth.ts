'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/useToast';
import { countProviderTrees } from '@/services/integrationMemory';
import {
  disconnectGoogleWorkspaceOAuth,
  fetchGoogleWorkspaceOAuthConfig,
  fetchGoogleWorkspaceOAuthStatus,
  openGoogleAuthorizationUrl,
  pollGoogleWorkspaceOAuthState,
  startGoogleWorkspaceOAuth,
} from '@/services/google-workspace-oauth';
import { apiRequest } from '@/lib/api';
import {
  OAUTH_POLL_INTERVAL_MS,
  OAUTH_POLL_TIMEOUT_MS,
  type OauthCredentialRecord,
  type OauthIntegration,
} from './credentialsConstants';

export function useCredentialsOAuth() {
  const t = useTranslations('settings.credentials');

  const [oauthCreds, setOauthCreds] = useState<OauthCredentialRecord[]>([]);
  const [isOauthLoading, setIsOauthLoading] = useState(false);
  const [connectModalTarget, setConnectModalTarget] = useState<OauthIntegration | null>(null);
  const [disconnectConfirmTarget, setDisconnectConfirmTarget] = useState<OauthIntegration | null>(null);
  const [clearSyncedMemory, setClearSyncedMemory] = useState(false);
  const [providerTreeCount, setProviderTreeCount] = useState(0);

  const [tokenInput, setTokenInput] = useState('');
  const [userIdInput, setUserIdInput] = useState('');
  const [scopeInput, setScopeInput] = useState('');
  const [googleOauthPolling, setGoogleOauthPolling] = useState(false);
  const [googleOauthConfigured, setGoogleOauthConfigured] = useState<boolean | null>(null);
  const [googleWorkspaceWriteEnabled, setGoogleWorkspaceWriteEnabled] = useState(false);
  const googlePollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (googlePollRef.current) clearInterval(googlePollRef.current);
    };
  }, []);

  const fetchOauthCreds = useCallback(async () => {
    try {
      setIsOauthLoading(true);
      const data = await apiRequest<OauthCredentialRecord[]>('/integrations/oauth', { silent: true });
      setOauthCreds(data || []);
      try {
        const gwStatus = await fetchGoogleWorkspaceOAuthStatus();
        setGoogleWorkspaceWriteEnabled(Boolean(gwStatus.connected && gwStatus.write_enabled));
      } catch {
        setGoogleWorkspaceWriteEnabled(false);
      }
    } catch (error) {
      console.error('Failed to load OAuth integrations:', error);
    } finally {
      setIsOauthLoading(false);
    }
  }, []);

  const handleConnectOauth = useCallback(async () => {
    if (!connectModalTarget) return;
    if (!tokenInput.trim()) {
      toast({ title: t('tokenRequired', { defaultValue: 'Token is required' }), variant: 'destructive' });
      return;
    }

    try {
      await apiRequest(`/integrations/oauth/${connectModalTarget.id}`, {
        method: 'POST',
        body: JSON.stringify({
          token: tokenInput.trim(),
          user_id: userIdInput.trim() || null,
          scope: scopeInput.trim() || null,
        }),
      });
      toast({ title: t('connectSuccess', { name: connectModalTarget.name }) });
      setConnectModalTarget(null);
      setTokenInput('');
      setUserIdInput('');
      setScopeInput('');
      fetchOauthCreds();
    } catch (error) {
      console.error('Failed to connect:', error);
      toast({ title: t('connectError', { name: connectModalTarget.name }), variant: 'destructive' });
    }
  }, [connectModalTarget, fetchOauthCreds, scopeInput, t, tokenInput, userIdInput]);

  const handleDisconnectOauth = useCallback(async () => {
    if (!disconnectConfirmTarget) return;

    try {
      const params = clearSyncedMemory ? '?clear_synced_memory=true' : '';
      if (disconnectConfirmTarget.oauthFlow === 'google_workspace') {
        await disconnectGoogleWorkspaceOAuth();
      } else {
        await apiRequest(`/integrations/oauth/${disconnectConfirmTarget.id}${params}`, {
          method: 'DELETE',
        });
      }
      toast({ title: t('disconnectSuccess', { name: disconnectConfirmTarget.name }) });
      setDisconnectConfirmTarget(null);
      setClearSyncedMemory(false);
      fetchOauthCreds();
    } catch (error) {
      console.error('Failed to disconnect:', error);
      toast({ title: t('disconnectError', { name: disconnectConfirmTarget.name }), variant: 'destructive' });
    }
  }, [clearSyncedMemory, disconnectConfirmTarget, fetchOauthCreds, t]);

  const handleGoogleWorkspaceConnect = useCallback(async (tier: 'readonly' | 'write' = 'readonly') => {
    setGoogleOauthPolling(true);
    try {
      const config = await fetchGoogleWorkspaceOAuthConfig();
      setGoogleOauthConfigured(config.configured);
      if (!config.configured) {
        toast({ title: t('googleOauthNotConfigured'), variant: 'destructive' });
        setGoogleOauthPolling(false);
        return;
      }

      const startRes = await startGoogleWorkspaceOAuth(tier);
      await openGoogleAuthorizationUrl(startRes.authorization_url);

      if (googlePollRef.current) clearInterval(googlePollRef.current);
      const pollStartedAt = Date.now();
      googlePollRef.current = setInterval(async () => {
        if (Date.now() - pollStartedAt > OAUTH_POLL_TIMEOUT_MS) {
          if (googlePollRef.current) clearInterval(googlePollRef.current);
          setGoogleOauthPolling(false);
          toast({ title: t('googleOauthTimeout'), variant: 'destructive' });
          return;
        }
        try {
          const statusRes = await pollGoogleWorkspaceOAuthState(startRes.state);
          if (statusRes.status === 'success') {
            if (googlePollRef.current) clearInterval(googlePollRef.current);
            setGoogleOauthPolling(false);
            setConnectModalTarget(null);
            if (statusRes.skill_was_user_disabled) {
              toast({ title: t('googleOauthConnectedSkillDisabled') });
            } else if (statusRes.skill_auto_enabled) {
              toast({
                title:
                  tier === 'write'
                    ? t('googleOauthWriteConnectedSkillEnabled')
                    : t('googleOauthConnectedSkillEnabled'),
              });
            } else {
              toast({
                title:
                  tier === 'write'
                    ? t('googleOauthWriteConnected')
                    : t('connectSuccess', { name: 'Google Workspace' }),
              });
            }
            fetchOauthCreds();
          } else if (statusRes.status === 'expired_or_invalid') {
            if (googlePollRef.current) clearInterval(googlePollRef.current);
            setGoogleOauthPolling(false);
            toast({ title: t('connectError', { name: 'Google Workspace' }), variant: 'destructive' });
          }
        } catch {
          // ignore polling errors
        }
      }, OAUTH_POLL_INTERVAL_MS);
    } catch (error) {
      setGoogleOauthPolling(false);
      toast({
        title: t('connectError', { name: 'Google Workspace' }),
        description: String(error),
        variant: 'destructive',
      });
    }
  }, [fetchOauthCreds, t]);

  const openConnectModal = useCallback(async (plat: OauthIntegration) => {
    setConnectModalTarget(plat);
    setTokenInput('');
    setUserIdInput('');
    setScopeInput('');
    if (plat.oauthFlow === 'google_workspace') {
      try {
        const config = await fetchGoogleWorkspaceOAuthConfig();
        setGoogleOauthConfigured(config.configured);
      } catch {
        setGoogleOauthConfigured(false);
      }
    } else {
      setGoogleOauthConfigured(null);
    }
  }, []);

  const prepareDisconnect = useCallback(async (plat: OauthIntegration) => {
    setDisconnectConfirmTarget(plat);
    try {
      const count = await countProviderTrees(plat.id);
      setProviderTreeCount(count);
    } catch {
      setProviderTreeCount(0);
    }
  }, []);

  const closeConnectModal = useCallback(() => {
    if (googlePollRef.current) clearInterval(googlePollRef.current);
    setGoogleOauthPolling(false);
    setConnectModalTarget(null);
    setTokenInput('');
    setUserIdInput('');
    setScopeInput('');
  }, []);

  return {
    clearSyncedMemory,
    closeConnectModal,
    connectModalTarget,
    disconnectConfirmTarget,
    fetchOauthCreds,
    googleOauthConfigured,
    googleOauthPolling,
    googleWorkspaceWriteEnabled,
    handleConnectOauth,
    handleDisconnectOauth,
    handleGoogleWorkspaceConnect,
    isOauthLoading,
    oauthCreds,
    openConnectModal,
    prepareDisconnect,
    providerTreeCount,
    scopeInput,
    setClearSyncedMemory,
    setDisconnectConfirmTarget,
    setScopeInput,
    setTokenInput,
    setUserIdInput,
    tokenInput,
    userIdInput,
  };
}
