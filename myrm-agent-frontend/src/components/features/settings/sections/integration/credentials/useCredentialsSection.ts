'use client';

import { useEffect, useMemo } from 'react';
import { useSkillStore } from '@/store/skill';
import { useCredentialsOAuth } from './useCredentialsOAuth';
import { useCredentialsStorage } from './useCredentialsStorage';

export function useCredentialsSection() {
  const storage = useCredentialsStorage();
  const oauth = useCredentialsOAuth();
  const { marketSkills, localSkills } = useSkillStore();

  useEffect(() => {
    storage.loadCredentials();
    storage.loadVaultCredentials();
    oauth.fetchOauthCreds();
  }, [oauth.fetchOauthCreds, storage.loadCredentials, storage.loadVaultCredentials]);

  const missingCredentials = useMemo(() => {
    const allSkills = [...marketSkills, ...localSkills];
    const missing = new Set<string>();

    allSkills.forEach((skill) => {
      if (skill.missing_credentials && skill.missing_credentials.length > 0) {
        skill.missing_credentials.forEach((cred) => {
          const filename = cred.split(' (')[0];
          if (!storage.credentials.find((item) => item.filename === filename)) {
            missing.add(filename);
          }
        });
      }
    });

    return Array.from(missing);
  }, [localSkills, marketSkills, storage.credentials]);

  return {
    ...storage,
    ...oauth,
    missingCredentials,
  };
}

export type CredentialsSectionState = ReturnType<typeof useCredentialsSection>;
