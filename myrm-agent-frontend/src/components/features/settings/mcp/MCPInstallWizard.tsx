import { useState, useCallback, useEffect, memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconLoader, IconShieldCheck, IconAlertTriangle } from '@/components/features/icons/PremiumIcons';
import { getMCPRegistryDetail, type MCPRegistryServerDetail } from '@/services/llm-config';
import type { MCPServiceConfig } from '@/store/config/types';

const SENSITIVE_KEYWORDS = ['key', 'secret', 'token', 'password', 'credential', 'auth'];

function isSensitiveField(name: string): boolean {
  const lower = name.toLowerCase();
  return SENSITIVE_KEYWORDS.some((kw) => lower.includes(kw));
}

interface MCPInstallWizardProps {
  qualifiedName: string;
  onInstall: (config: MCPServiceConfig) => void;
  onCancel: () => void;
}

export const MCPInstallWizard = memo(function MCPInstallWizard({
  qualifiedName,
  onInstall,
  onCancel,
}: MCPInstallWizardProps) {
  const t = useTranslations('settings');
  const [detail, setDetail] = useState<MCPRegistryServerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getMCPRegistryDetail(qualifiedName)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        const initial: Record<string, string> = {};
        d.envVars.forEach((ev) => {
          initial[ev.name] = '';
        });
        setEnvValues(initial);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : t('mcpRegistryLoadFailed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [qualifiedName, t]);

  const handleInstall = useCallback(async () => {
    if (!detail) return;

    const missingRequired = detail.envVars.filter((ev) => ev.required && !envValues[ev.name]?.trim());
    if (missingRequired.length > 0) {
      setError(t('mcpRegistryMissingRequired', { fields: missingRequired.map((v) => v.name).join(', ') }));
      return;
    }

    setInstalling(true);
    setError(null);

    try {
      const config: MCPServiceConfig = buildConfigFromDetail(detail, envValues);
      onInstall(config);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Install failed');
    } finally {
      setInstalling(false);
    }
  }, [detail, envValues, onInstall, t]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-sm">
        <IconLoader className="w-5 h-5 animate-spin mb-2" />
        {t('mcpRegistryLoadingDetail')}
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="flex flex-col items-center py-8 space-y-3">
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
        <button onClick={onCancel} className="text-sm text-primary hover:underline">
          {t('mcpRegistryBackToList')}
        </button>
      </div>
    );
  }

  if (!detail) return null;

  return (
    <div className="space-y-5">
      <div className="flex items-center space-x-3">
        {detail.iconUrl ? (
          <img src={detail.iconUrl} alt="" className="w-10 h-10 rounded-lg object-contain bg-muted" />
        ) : (
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <IconShieldCheck className="w-5 h-5 text-primary" />
          </div>
        )}
        <div>
          <h3 className="text-base font-semibold text-foreground">{detail.displayName}</h3>
          <p className="text-xs text-muted-foreground">{detail.qualifiedName}</p>
        </div>
      </div>

      {detail.description && (
        <p className="text-sm text-muted-foreground leading-relaxed">{detail.description}</p>
      )}

      <div className="flex items-center gap-2 text-xs text-muted-foreground bg-secondary rounded-lg px-3 py-2">
        <span className="font-medium">{t('mcpRegistryTransport')}:</span>
        <span className="px-2 py-0.5 rounded bg-primary/10 text-primary font-mono">
          {detail.transportType}
        </span>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/30 px-3 py-2.5">
        <IconAlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
        <p className="text-xs text-amber-700 dark:text-amber-300">{t('mcpRegistrySecurityNotice')}</p>
      </div>

      {detail.envVars.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-foreground">{t('mcpRegistryConfiguration')}</h4>
          {detail.envVars.map((ev) => (
            <div key={ev.name} className="space-y-1">
              <label className="flex items-center gap-1 text-xs font-medium text-foreground">
                {ev.name}
                {ev.required && <span className="text-destructive">*</span>}
              </label>
              {ev.description && (
                <p className="text-[11px] text-muted-foreground">{ev.description}</p>
              )}
              <input
                type={isSensitiveField(ev.name) ? 'password' : 'text'}
                value={envValues[ev.name] ?? ''}
                onChange={(e) => setEnvValues((prev) => ({ ...prev, [ev.name]: e.target.value }))}
                placeholder={ev.required ? t('mcpRegistryRequired') : t('mcpRegistryOptional')}
                className="w-full rounded-lg border border-border bg-secondary px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 font-mono"
              />
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          onClick={onCancel}
          className="px-4 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          {t('mcpCancel')}
        </button>
        <button
          onClick={handleInstall}
          disabled={installing}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {installing && <IconLoader className="w-3.5 h-3.5 animate-spin" />}
          {t('mcpRegistryInstallAndScan')}
        </button>
      </div>
    </div>
  );
});

function buildConfigFromDetail(
  detail: MCPRegistryServerDetail,
  envValues: Record<string, string>,
): MCPServiceConfig {
  const friendlyName = detail.displayName.replace(/[^a-zA-Z0-9_-]/g, '-').toLowerCase().slice(0, 50);

  const type = detail.transportType === 'stdio' ? 'stdio' as const : 'streamable_http' as const;

  const config: MCPServiceConfig = {
    name: friendlyName,
    type,
    description: detail.description || detail.displayName,
    enabled: true,
  };

  if (type === 'stdio') {
    config.command = 'npx';
    config.args = ['-y', detail.qualifiedName];
  } else {
    const baseUrl = `https://server.smithery.ai/${detail.qualifiedName}`;
    const configPayload = btoa(JSON.stringify(envValues));
    config.url = `${baseUrl}/mcp?config=${configPayload}`;
  }

  const envEntries = Object.entries(envValues).filter(([, v]) => v.trim());
  const extra: Record<string, unknown> = { registryQualifiedName: detail.qualifiedName };
  if (type === 'stdio') {
    for (const [k, v] of envEntries) extra[k] = v;
  }
  config.extra_params = extra;

  return config;
}
