'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Fingerprint, Link2, Loader2, Trash2 } from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import {
  type OrgOidcConfig,
  type OrgMember,
  deleteOrgSsoConfig,
  getMyOrg,
  getOrgSsoConfig,
  listMembers,
  upsertOrgSsoConfig,
} from '@/services/enterprise-org';
import { canManageOrgMcp } from './orgMcpAccess';
import useAuthStore from '@/store/useAuthStore';

function parseGroups(raw: string): string[] | undefined {
  const groups = raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  return groups.length > 0 ? groups : undefined;
}

function formatGroups(groups: string[] | undefined): string {
  return groups?.join(', ') ?? '';
}

function maskSecret(masked: string): string {
  return masked && masked.length > 4 ? `••••••${masked.slice(-4)}` : '••••••';
}

const EnterpriseSsoTab = memo(() => {
  const t = useTranslations('settings.enterprise.sso');
  const authUserId = useAuthStore((s) => s.user?.id);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const isOrgAdmin = useMemo(
    () => canManageOrgMcp(members, authUserId),
    [authUserId, members],
  );

  const [orgId, setOrgId] = useState('');
  const [config, setConfig] = useState<OrgOidcConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [issuerUrl, setIssuerUrl] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [autoProvision, setAutoProvision] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [allowedGroups, setAllowedGroups] = useState('');

  const cpBaseUrl = resolveCpBaseUrl();
  const loginLink = useMemo(
    () =>
      orgId
        ? `${cpBaseUrl}/api/auth/oauth/oidc/authorize?org=${encodeURIComponent(orgId)}`
        : '',
    [cpBaseUrl, orgId],
  );

  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      const org = await getMyOrg();
      setOrgId(org.id);
      const [sso, memberRows] = await Promise.all([
        getOrgSsoConfig(org.id),
        listMembers(org.id),
      ]);
      setMembers(memberRows);
      setConfig(sso);
      if (sso) {
        setIssuerUrl(sso.issuer_url);
        setClientId(sso.client_id);
        setClientSecret('');
        setAutoProvision(sso.auto_provision);
        setEnabled(sso.enabled);
        setAllowedGroups(formatGroups(sso.allowed_groups));
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const handleSave = useCallback(async () => {
    if (!orgId || !issuerUrl.trim() || !clientId.trim()) return;
    setSaving(true);
    try {
      const saved = await upsertOrgSsoConfig(orgId, {
        issuer_url: issuerUrl.trim(),
        client_id: clientId.trim(),
        client_secret: clientSecret.trim(),
        auto_provision: autoProvision,
        enabled,
        allowed_groups: parseGroups(allowedGroups),
      });
      setConfig(saved);
      setClientSecret('');
      setAutoProvision(saved.auto_provision);
      setEnabled(saved.enabled);
      setAllowedGroups(formatGroups(saved.allowed_groups));
      toast.success(t('saved'));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('saveFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, issuerUrl, clientId, clientSecret, autoProvision, enabled, allowedGroups, t]);

  const handleDelete = useCallback(async () => {
    if (!orgId) return;
    try {
      await deleteOrgSsoConfig(orgId);
      setConfig(null);
      setIssuerUrl('');
      setClientId('');
      setClientSecret('');
      setAutoProvision(true);
      setEnabled(true);
      setAllowedGroups('');
      toast.success(t('deleted'));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('deleteFailed'));
    }
  }, [orgId, t]);

  const copyLoginLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(loginLink);
      toast.success(t('loginLinkCopied'));
    } catch {
      toast.error(t('loginLinkCopyFailed'));
    }
  }, [loginLink, t]);

  if (loading) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-muted rounded w-1/3" />
          <div className="h-20 bg-muted rounded" />
        </div>
      </SettingsSection>
    );
  }

  if (!isOrgAdmin) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <p className="text-sm text-muted-foreground">{t('adminOnly')}</p>
      </SettingsSection>
    );
  }

  return (
    <SettingsSection
      title={
        <span className="flex items-center gap-2">
          <Fingerprint className="h-5 w-5" />
          {t('title')}
        </span>
      }
      description={t('description')}
    >
      <div className="space-y-5">
        {config === null && <p className="text-sm text-muted-foreground">{t('notConfigured')}</p>}

        <div className="grid gap-4">
          <div className="space-y-2">
            <Label htmlFor="sso-issuer">{t('issuerLabel')}</Label>
            <Input
              id="sso-issuer"
              value={issuerUrl}
              onChange={(e) => setIssuerUrl(e.target.value)}
              placeholder={t('issuerHint')}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="sso-client-id">{t('clientIdLabel')}</Label>
            <Input
              id="sso-client-id"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder={t('clientIdPlaceholder')}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="sso-client-secret">{t('secretLabel')}</Label>
            <Input
              id="sso-client-secret"
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder={
                config && config.client_secret_masked
                  ? maskSecret(config.client_secret_masked)
                  : t('secretPlaceholder')
              }
            />
            <p className="text-xs text-muted-foreground">
              {config && config.client_secret_masked
                ? t('secretKeepHint', { masked: maskSecret(config.client_secret_masked) })
                : t('secretPlaceholderHint')}
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="sso-groups">{t('groupsLabel')}</Label>
            <Input
              id="sso-groups"
              value={allowedGroups}
              onChange={(e) => setAllowedGroups(e.target.value)}
              placeholder="engineering, finance"
            />
            <p className="text-xs text-muted-foreground">{t('groupsHint')}</p>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border/40 px-4 py-3">
            <div>
              <p className="text-sm font-medium">{t('autoProvisionLabel')}</p>
              <p className="text-xs text-muted-foreground">{t('autoProvisionHint')}</p>
            </div>
            <Switch checked={autoProvision} onCheckedChange={setAutoProvision} />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border/40 px-4 py-3">
            <div>
              <p className="text-sm font-medium">{t('enabledLabel')}</p>
              <p className="text-xs text-muted-foreground">{t('enabledHint')}</p>
            </div>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={handleSave} disabled={saving || !issuerUrl.trim() || !clientId.trim()}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            {t('save')}
          </Button>
          {config !== null && (
            <Button variant="destructive" onClick={handleDelete}>
              <Trash2 className="h-4 w-4 mr-1" />
              {t('remove')}
            </Button>
          )}
        </div>

        {config !== null && loginLink && (
          <div className="space-y-2 rounded-lg bg-muted/50 border border-border/40 p-4">
            <div className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-medium">{t('loginLink')}</p>
              <Badge
                className={cn(
                  config.enabled
                    ? 'bg-primary/10 text-primary border-primary/20'
                    : 'bg-muted text-muted-foreground border-border/40',
                )}
              >
                {config.enabled ? t('configured') : t('disabled')}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">{t('loginLinkHint')}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-background px-2 py-1.5 rounded break-all">
                {loginLink}
              </code>
              <Button size="sm" variant="outline" onClick={copyLoginLink}>
                {t('copyLink')}
              </Button>
            </div>
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

EnterpriseSsoTab.displayName = 'EnterpriseSsoTab';

export default EnterpriseSsoTab;
