'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Alert, AlertDescription } from '@/components/primitives/alert';
import { cn } from '@/lib/utils';
import { OAuthProviderIcon } from '@/components/auth/oauth-provider-icons';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';

type AuthConfigResponse = {
  edition?: string;
  oauth_providers?: string[];
};

type OAuthButtonsProps = {
  redirectPath?: string;
};

const providerStyles: Record<string, string> = {
  google:
    'border-border/80 bg-background hover:bg-muted/60 dark:bg-card/80 dark:hover:bg-muted/40',
  github:
    'border-border/80 bg-background hover:bg-muted/60 dark:bg-card/80 dark:hover:bg-muted/40',
  oidc:
    'border-primary/30 bg-primary/5 hover:bg-primary/10 dark:border-primary/40 dark:bg-primary/10',
};

export default function OAuthButtons({ redirectPath = '/' }: OAuthButtonsProps) {
  const cpBaseUrl = resolveCpBaseUrl();
  const t = useTranslations('auth.oauth');
  const [providers, setProviders] = useState<string[]>([]);
  const [edition, setEdition] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [configError, setConfigError] = useState(false);
  const [pendingProvider, setPendingProvider] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${cpBaseUrl}/api/auth/config`);
        if (!response.ok) {
          if (!cancelled) {
            setConfigError(true);
          }
          return;
        }
        const data = (await response.json()) as AuthConfigResponse;
        if (!cancelled) {
          setEdition(data.edition ?? null);
          setProviders(data.oauth_providers ?? []);
        }
      } catch {
        if (!cancelled) {
          setConfigError(true);
          setProviders([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cpBaseUrl]);

  const startOAuth = useCallback(
    (provider: string) => {
      setPendingProvider(provider);
      const redirect = encodeURIComponent(redirectPath);
      window.location.href = `${cpBaseUrl}/api/auth/oauth/${provider}/authorize?redirect=${redirect}`;
    },
    [cpBaseUrl, redirectPath],
  );

  if (loading) {
    return (
      <div className="flex justify-center py-3">
        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const showUnavailableHint =
    configError
    || ((edition === 'saas' || edition === 'enterprise') && providers.length === 0);

  if (providers.length === 0) {
    if (!showUnavailableHint) {
      return null;
    }
    return (
      <Alert
        variant="destructive"
        className="border-amber-500/40 bg-amber-500/5 text-amber-900 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-100"
      >
        <AlertDescription className="text-sm leading-relaxed">
          {t('unavailableHint')}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="grid gap-2.5">
      {providers.map((provider) => (
        <Button
          key={provider}
          type="button"
          variant="outline"
          className={cn(
            'w-full h-11 font-medium transition-all duration-200 shadow-sm',
            providerStyles[provider] ?? providerStyles.google,
          )}
          disabled={pendingProvider !== null}
          onClick={() => startOAuth(provider)}
        >
          {pendingProvider === provider ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <span className="inline-flex items-center justify-center gap-2.5">
              <OAuthProviderIcon provider={provider} className="w-4 h-4 shrink-0" />
              <span>{t(`provider.${provider}`, { default: `Continue with ${provider}` })}</span>
            </span>
          )}
        </Button>
      ))}
    </div>
  );
}
