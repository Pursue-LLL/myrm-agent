'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { getConfigSyncManager } from '@/services/config';
import type { SecurityDashboardSettingsConfigValue } from '@/services/config/types';
import type { SecuritySetupHints } from './types';

const MAX_REPOS = 3;

export function normalizeRepoInput(raw: string): string | null {
  const slug = raw.trim();
  if (!slug.includes('/')) return null;
  const [owner, name] = slug.split('/', 2);
  if (!owner?.trim() || !name?.trim()) return null;
  return `${owner.trim()}/${name.trim()}`;
}

interface SecuritySetupPanelProps {
  setupHints: SecuritySetupHints;
  urlCopied: boolean;
  onCopyWebhookUrl: () => void;
}

function RepoEditor({
  repoInputs,
  setRepoInputs,
  repoError,
  saveMessage,
  onSave,
}: {
  repoInputs: string[];
  setRepoInputs: (value: string[]) => void;
  repoError: string | null;
  saveMessage: string | null;
  onSave: () => void;
}) {
  const t = useTranslations('securityDashboard');

  return (
    <>
      {repoInputs.map((value, index) => (
        <input
          key={index}
          type="text"
          value={value}
          onChange={(e) => {
            const next = [...repoInputs];
            next[index] = e.target.value;
            setRepoInputs(next);
          }}
          placeholder={t('monitoredReposPlaceholder')}
          className="w-full px-3 py-2 text-sm rounded-lg border bg-background font-mono"
        />
      ))}
      {repoInputs.length < MAX_REPOS && (
        <button
          type="button"
          onClick={() => setRepoInputs([...repoInputs, ''])}
          className="text-sm text-primary hover:underline"
        >
          {t('monitoredReposAdd')}
        </button>
      )}
      {repoError && <p className="text-xs text-red-500">{repoError}</p>}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          className="px-3 py-2 text-sm rounded-lg border hover:bg-accent"
        >
          {t('monitoredReposSave')}
        </button>
        {saveMessage && <span className="text-xs text-green-600 dark:text-green-500">{saveMessage}</span>}
      </div>
    </>
  );
}

export function SecuritySetupPanel({
  setupHints,
  urlCopied,
  onCopyWebhookUrl,
}: SecuritySetupPanelProps) {
  const t = useTranslations('securityDashboard');
  const [repoInputs, setRepoInputs] = useState<string[]>(['']);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [repoError, setRepoError] = useState<string | null>(null);
  const [configReady, setConfigReady] = useState(false);

  const loadRepos = useCallback(() => {
    const syncManager = getConfigSyncManager();
    const raw = syncManager.get('securityDashboardSettings') as SecurityDashboardSettingsConfigValue | null;
    const repos = Array.isArray(raw?.monitoredGithubRepos) ? raw.monitoredGithubRepos : [];
    setRepoInputs(repos.length > 0 ? repos : ['']);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const init = async () => {
      const syncManager = getConfigSyncManager();
      if (!syncManager.isInitialized) {
        try {
          await syncManager.initialize();
        } catch (err) {
          console.error('Failed to initialize config for security dashboard:', err);
        }
      }
      if (!cancelled) {
        loadRepos();
        setConfigReady(true);
      }
    };

    void init();
    const syncManager = getConfigSyncManager();
    const unsubscribe = syncManager.subscribe('securityDashboardSettings', () => {
      loadRepos();
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [loadRepos]);

  const saveRepos = async () => {
    setRepoError(null);
    setSaveMessage(null);
    const seen = new Set<string>();
    const cleaned: string[] = [];
    const invalid: string[] = [];

    for (const input of repoInputs) {
      const trimmed = input.trim();
      if (!trimmed) continue;
      const slug = normalizeRepoInput(input);
      if (!slug) {
        invalid.push(trimmed);
        continue;
      }
      if (!seen.has(slug)) {
        seen.add(slug);
        cleaned.push(slug);
      }
      if (cleaned.length >= MAX_REPOS) break;
    }

    if (invalid.length > 0) {
      setRepoError(t('monitoredReposInvalid', { example: 'my-org/my-app' }));
      return;
    }

    const syncManager = getConfigSyncManager();
    syncManager.set('securityDashboardSettings', { monitoredGithubRepos: cleaned });

    try {
      const result = await syncManager.forceSync();
      if (!result.success) {
        setRepoError(t('monitoredReposSyncFailed'));
        return;
      }
      setSaveMessage(t('monitoredReposSaved'));
      setTimeout(() => setSaveMessage(null), 2500);
    } catch (err) {
      console.error('Failed to sync securityDashboardSettings:', err);
      setRepoError(t('monitoredReposSyncFailed'));
    }
  };

  if (!configReady) {
    return (
      <div className="rounded-xl border border-border/60 bg-muted/20 p-4 md:p-6">
        <div className="h-6 w-48 rounded bg-muted animate-pulse" />
      </div>
    );
  }

  const repoBlock = (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">{t('monitoredReposTitle')}</h3>
      <p className="text-xs text-muted-foreground">{t('monitoredReposHint')}</p>
      <RepoEditor
        repoInputs={repoInputs}
        setRepoInputs={setRepoInputs}
        repoError={repoError}
        saveMessage={saveMessage}
        onSave={saveRepos}
      />
    </div>
  );

  if (!setupHints.isSandbox) {
    return (
      <div className="rounded-xl border border-border/60 bg-muted/20 p-4 md:p-6 space-y-4">
        <h2 className="text-lg font-semibold">{t('monitoredReposTitle')}</h2>
        <p className="text-sm text-muted-foreground">{t('monitoredReposHint')}</p>
        <RepoEditor
          repoInputs={repoInputs}
          setRepoInputs={setRepoInputs}
          repoError={repoError}
          saveMessage={saveMessage}
          onSave={saveRepos}
        />
        {!setupHints.githubTokenConfigured && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            {t('setupToken')}{' '}
            <Link href="/settings/credentials" className="text-primary underline underline-offset-2">
              {t('openSettingsCredentials')}
            </Link>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-primary/25 bg-gradient-to-br from-primary/8 via-background to-background p-4 md:p-6 space-y-4 shadow-sm">
      <h2 className="text-lg font-semibold">{t('setupTitle')}</h2>
      {!setupHints.cpIngressConfigured && (
        <p className="text-sm text-amber-600 dark:text-amber-400">{t('noIngress')}</p>
      )}
      {setupHints.webhookTenantId && (
        <p className="text-sm text-muted-foreground">
          {t('setupTenant')}: <span className="font-mono">{setupHints.webhookTenantId}</span>
        </p>
      )}
      {setupHints.webhookUrl && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="flex-1 min-w-0">
            <p className="text-xs text-muted-foreground mb-1">{t('setupUrl')}</p>
            <code className="text-xs break-all block p-2 rounded bg-background border">
              {setupHints.webhookUrl}
            </code>
          </div>
          <button
            type="button"
            onClick={onCopyWebhookUrl}
            className="px-3 py-2 text-sm rounded-lg border hover:bg-accent shrink-0"
          >
            {urlCopied ? t('copied') : t('copyUrl')}
          </button>
        </div>
      )}
      <p className="text-xs text-muted-foreground">{t('setupSecret', { env: setupHints.cpWebhookSecretEnv })}</p>
      {!setupHints.githubTokenConfigured && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          {t('setupToken')}{' '}
          <Link href="/settings/credentials" className="text-primary underline underline-offset-2">
            {t('openSettingsCredentials')}
          </Link>
        </p>
      )}
      <div className="pt-2 border-t border-border/50">{repoBlock}</div>
    </div>
  );
}
