'use client';

import { useEffect } from 'react';
import { useCredentialsOAuth } from './useCredentialsOAuth';
import { useCredentialsStorage } from './useCredentialsStorage';

export function useCredentialsSection() {
  const storage = useCredentialsStorage();
  const oauth = useCredentialsOAuth();
  const { loadCredentials, loadVaultCredentials } = storage;
  const { fetchOauthCreds } = oauth;

  useEffect(() => {
    loadCredentials();
    loadVaultCredentials();
    fetchOauthCreds();
  }, [fetchOauthCreds, loadCredentials, loadVaultCredentials]);

  return {
    ...storage,
    ...oauth,
  };
}

export type CredentialsSectionState = ReturnType<typeof useCredentialsSection>;
