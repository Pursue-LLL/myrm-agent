'use client';

import { memo, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { IconUpload, IconTrash, IconAlertCircle, IconCheckCircle, IconClock } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { toast } from '@/hooks/useToast';
import SettingsSection from './SettingsSection';
import { cn } from '@/lib/utils';
import { localizeReactNode } from '@/lib/utils/localeText';
import { uploadCredential, listCredentials, deleteCredential, type CredentialFile, listVaultCredentials, createVaultCredential, updateVaultCredential, deleteVaultCredential, type VaultCredential } from '@/services/credentials';
import { countProviderTrees } from '@/services/integrationMemory';
import { useSkillStore } from '@/store/skill';
import { apiRequest } from '@/lib/api';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import { Checkbox } from '@/components/primitives/checkbox';
const SUPPORTED_INTEGRATIONS = [
  {
    id: 'feishu',
    name: 'Feishu / 飞书',
    desc: 'Sync docs, messages, and automate tasks',
    descZh: '同步飞书文档、消息及执行自动化任务',
    category: 'communication',
  },
  {
    id: 'dingtalk',
    name: 'DingTalk / 钉钉',
    desc: 'Automate messages, work items, and workflows',
    descZh: '同步钉钉消息、工作项及审批流',
    category: 'communication',
  },
  {
    id: 'github',
    name: 'GitHub',
    desc: 'Manage repositories, issues, and PRs',
    descZh: '管理 GitHub 代码库、Issues 及 Pull Requests',
    category: 'development',
  },
  {
    id: 'jira',
    name: 'Jira',
    desc: 'Sync issues, backlogs, and agile boards',
    descZh: '同步 Jira 问题、待办事项及敏捷看板',
    category: 'productivity',
  },
  {
    id: 'slack',
    name: 'Slack',
    desc: 'Send channel alerts and automate team chat',
    descZh: '发送 Slack 渠道提醒并自动化团队沟通',
    category: 'communication',
  },
];

const CredentialsSection = memo(() => {
  const t = useTranslations('settings.credentials');
  const locale = useLocale();
  const { marketSkills, localSkills } = useSkillStore();

  const [credentials, setCredentials] = useState<CredentialFile[]>([]);
  const [vaultCredentials, setVaultCredentials] = useState<VaultCredential[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isVaultLoading, setIsVaultLoading] = useState(true);
  
  const [vaultModalOpen, setVaultModalOpen] = useState(false);
  const [editingVaultCred, setEditingVaultCred] = useState<VaultCredential | null>(null);
  const [vaultLabel, setVaultLabel] = useState('');
  const [vaultPassword, setVaultPassword] = useState('');
  const [vaultTotp, setVaultTotp] = useState('');
  const [vaultDesc, setVaultDesc] = useState('');
  const [deleteVaultTarget, setDeleteVaultTarget] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadingFilename, setUploadingFilename] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const [oauthCreds, setOauthCreds] = useState<any[]>([]);
  const [isOauthLoading, setIsOauthLoading] = useState(false);
  const [connectModalTarget, setConnectModalTarget] = useState<any | null>(null);
  const [disconnectConfirmTarget, setDisconnectConfirmTarget] = useState<any | null>(null);
  const [clearSyncedMemory, setClearSyncedMemory] = useState(false);
  const [providerTreeCount, setProviderTreeCount] = useState(0);

  const [tokenInput, setTokenInput] = useState('');
  const [userIdInput, setUserIdInput] = useState('');
  const [scopeInput, setScopeInput] = useState('');

  const fetchOauthCreds = useCallback(async () => {
    try {
      setIsOauthLoading(true);
      const data = await apiRequest<any[]>('/oauth', { silent: true });
      setOauthCreds(data || []);
    } catch (e) {
      console.error('Failed to load OAuth integrations:', e);
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
      await apiRequest(`/oauth/${connectModalTarget.id}`, {
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
    } catch (e) {
      console.error('Failed to connect:', e);
      toast({ title: t('connectError', { name: connectModalTarget.name }), variant: 'destructive' });
    }
  }, [connectModalTarget, tokenInput, userIdInput, scopeInput, t, fetchOauthCreds]);

  const handleDisconnectOauth = useCallback(async () => {
    if (!disconnectConfirmTarget) return;

    try {
      const params = clearSyncedMemory ? '?clear_synced_memory=true' : '';
      await apiRequest(`/oauth/${disconnectConfirmTarget.id}${params}`, {
        method: 'DELETE',
      });
      toast({ title: t('disconnectSuccess', { name: disconnectConfirmTarget.name }) });
      setDisconnectConfirmTarget(null);
      setClearSyncedMemory(false);
      fetchOauthCreds();
    } catch (e) {
      console.error('Failed to disconnect:', e);
      toast({ title: t('disconnectError', { name: disconnectConfirmTarget.name }), variant: 'destructive' });
    }
  }, [disconnectConfirmTarget, clearSyncedMemory, t, fetchOauthCreds]);

  const loadCredentials = useCallback(async () => {
    try {
      setIsLoading(true);
      const files = await listCredentials();
      setCredentials(files);
    } catch (error) {
      console.error('Failed to load credentials:', error);
      toast({
        title: t('loadError', { defaultValue: 'Failed to load credentials' }),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  const loadVaultCredentials = useCallback(async () => {
    try {
      setIsVaultLoading(true);
      const creds = await listVaultCredentials();
      setVaultCredentials(creds);
    } catch (error) {
      console.error('Failed to load vault credentials:', error);
    } finally {
      setIsVaultLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCredentials();
    loadVaultCredentials();
    fetchOauthCreds();
  }, [loadCredentials, loadVaultCredentials, fetchOauthCreds]);

  const handleSaveVaultCredential = async () => {
    if (!vaultLabel.trim()) {
      toast({ title: 'Label is required', variant: 'destructive' });
      return;
    }
    if (!vaultPassword.trim() && !vaultTotp.trim()) {
      toast({ title: 'Password or TOTP seed is required', variant: 'destructive' });
      return;
    }

    try {
      if (editingVaultCred) {
        await updateVaultCredential(editingVaultCred.label, {
          password: vaultPassword || undefined,
          totp_seed: vaultTotp || undefined,
          description: vaultDesc || undefined,
        });
        toast({ title: 'Vault credential updated' });
      } else {
        await createVaultCredential({
          label: vaultLabel.trim(),
          password: vaultPassword || undefined,
          totp_seed: vaultTotp || undefined,
          description: vaultDesc || undefined,
        });
        toast({ title: 'Vault credential created' });
      }
      setVaultModalOpen(false);
      loadVaultCredentials();
    } catch (e: any) {
      toast({ title: e.message || 'Failed to save vault credential', variant: 'destructive' });
    }
  };

  const handleDeleteVaultConfirm = async () => {
    if (!deleteVaultTarget) return;
    try {
      await deleteVaultCredential(deleteVaultTarget);
      toast({ title: 'Vault credential deleted' });
      loadVaultCredentials();
    } catch (e: any) {
      toast({ title: e.message || 'Failed to delete vault credential', variant: 'destructive' });
    } finally {
      setDeleteVaultTarget(null);
    }
  };

  const handleUpload = useCallback(
    async (targetFilename: string) => {
      if (!fileInputRef.current) return;

      setUploadingFilename(targetFilename);
      fileInputRef.current.accept = '*';
      fileInputRef.current.onchange = async (e: Event) => {
        const input = e.target as HTMLInputElement;
        const file = input.files?.[0];
        if (!file) {
          setUploadingFilename(null);
          return;
        }

        try {
          setIsUploading(true);
          await uploadCredential(file, targetFilename);
          toast({
            title: t('uploadSuccess', { defaultValue: 'Credential uploaded successfully' }),
          });
          await loadCredentials();
        } catch (error) {
          console.error('Failed to upload credential:', error);
          toast({
            title: t('uploadError', { defaultValue: 'Failed to upload credential' }),
            variant: 'destructive',
          });
        } finally {
          setIsUploading(false);
          setUploadingFilename(null);
          input.value = '';
        }
      };

      fileInputRef.current.click();
    },
    [t, loadCredentials],
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return;

    try {
      await deleteCredential(deleteTarget);
      toast({
        title: t('deleteSuccess', { defaultValue: 'Credential deleted' }),
      });
      await loadCredentials();
    } catch (error) {
      console.error('Failed to delete credential:', error);
      toast({
        title: t('deleteError', { defaultValue: 'Failed to delete credential' }),
        variant: 'destructive',
      });
      throw error;
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, t, loadCredentials]);

  const missingCredentials = useMemo(() => {
    const allSkills = [...marketSkills, ...localSkills];
    const missing = new Set<string>();

    allSkills.forEach((skill) => {
      if (skill.missing_credentials && skill.missing_credentials.length > 0) {
        skill.missing_credentials.forEach((cred) => {
          const filename = cred.split(' (')[0];
          if (!credentials.find((c) => c.filename === filename)) {
            missing.add(filename);
          }
        });
      }
    });

    return Array.from(missing);
  }, [marketSkills, localSkills, credentials]);

  return localizeReactNode(
    <SettingsSection title={t('title')} description={t('description')}>
      <input ref={fileInputRef} type="file" className="hidden" aria-label="Credential file input" />

      <div className="space-y-6">
        {/* Form Credentials Vault Section */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium flex items-center gap-2">
              <IconCheckCircle className="h-5 w-5 text-primary" />
              Form Credentials Vault (Zero-Disk)
              <Badge variant="secondary" className="ml-auto">
                {vaultCredentials.length}
              </Badge>
            </h3>
            <Button size="sm" onClick={() => {
              setEditingVaultCred(null);
              setVaultLabel('');
              setVaultPassword('');
              setVaultTotp('');
              setVaultDesc('');
              setVaultModalOpen(true);
            }}>
              + Add Credential
            </Button>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Securely store passwords and TOTP seeds for browser/desktop automation. Secrets are encrypted and never exposed to the LLM context.
          </p>

          {isVaultLoading ? (
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="flex items-center gap-3 p-3 rounded-lg border">
                  <div className="h-10 w-10 rounded bg-muted animate-pulse" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                    <div className="h-3 w-20 bg-muted animate-pulse rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : vaultCredentials.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground border rounded-lg border-dashed">No form credentials stored.</div>
          ) : (
            <div className="space-y-2">
              {vaultCredentials.map((cred) => (
                <div
                  key={cred.id}
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <div className="font-mono text-sm font-medium">{cred.label}</div>
                      {cred.has_password && <Badge variant="outline" className="text-xs">Password</Badge>}
                      {cred.has_totp_seed && <Badge variant="outline" className="text-xs">TOTP</Badge>}
                    </div>
                    {cred.description && <div className="text-xs text-muted-foreground mt-1">{cred.description}</div>}
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingVaultCred(cred);
                        setVaultLabel(cred.label);
                        setVaultPassword(''); // Don't show existing password
                        setVaultTotp(''); // Don't show existing TOTP
                        setVaultDesc(cred.description || '');
                        setVaultModalOpen(true);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleteVaultTarget(cred.label)}
                      className="text-red-500 hover:text-red-700 hover:bg-red-500/10"
                    >
                      <IconTrash className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-border pt-6">
          <h3 className="font-medium mb-3 flex items-center gap-2">
            <IconCheckCircle className="h-5 w-5 text-green-500" />
            {t('uploadedTitle')} (Files)
            <Badge variant="secondary" className="ml-auto">
              {credentials.length}
            </Badge>
          </h3>

          {missingCredentials.length > 0 && (
            <div className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-4 mb-4">
              <div className="flex items-start gap-3">
                <IconAlertCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h3 className="font-medium text-amber-500 mb-2">{t('missingTitle')}</h3>
                  <div className="space-y-2">
                    {missingCredentials.map((filename) => (
                      <div key={filename} className="flex items-center justify-between p-2 rounded bg-background/50">
                        <span className="text-sm font-mono">{filename}</span>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleUpload(filename)}
                          disabled={isUploading && uploadingFilename === filename}
                        >
                          <IconUpload className="h-4 w-4 mr-2" />
                          {t('upload')}
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3 p-3 rounded-lg border">
                  <div className="h-10 w-10 rounded bg-muted animate-pulse" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                    <div className="h-3 w-20 bg-muted animate-pulse rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : credentials.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">{t('noCredentials')}</div>
          ) : (
            <div className="space-y-2">
              {credentials.map((cred) => {
                const getExpiryBadge = () => {
                  if (!cred.expiry_status || cred.expiry_status === 'error') return null;

                  if (cred.expiry_status === 'valid') {
                    return (
                      <Badge variant="outline" className="text-green-600 border-green-600">
                        <IconCheckCircle className="h-3 w-3 mr-1" />
                        {t('valid')}
                      </Badge>
                    );
                  }

                  if (cred.expiry_status === 'expiring_soon') {
                    return (
                      <Badge variant="outline" className="text-amber-600 border-amber-600">
                        <IconClock className="h-3 w-3 mr-1" />
                        {t('expiringSoon', { days: String(cred.remaining_days) })}
                      </Badge>
                    );
                  }

                  if (cred.expiry_status === 'expired') {
                    return (
                      <Badge variant="outline" className="text-red-600 border-red-600">
                        <IconAlertCircle className="h-3 w-3 mr-1" />
                        {t('expired')}
                      </Badge>
                    );
                  }

                  return null;
                };

                return (
                  <div
                    key={cred.filename}
                    className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <div className="font-mono text-sm font-medium">{cred.filename}</div>
                        {getExpiryBadge()}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">{(cred.size / 1024).toFixed(2)} KB</div>
                    </div>

                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleteTarget(cred.filename)}
                      className="text-red-500 hover:text-red-700 hover:bg-red-500/10"
                    >
                      <IconTrash className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* SaaS / Enterprise Integrations Section was removed and migrated to ToolCapabilitiesSection */}
      <div className="mt-8 pt-8 border-t border-border">
        <h3 className="text-lg font-semibold flex items-center gap-2 text-foreground">{t('oauthTitle')}</h3>
        <p className="text-sm text-muted-foreground mt-1 mb-6 leading-relaxed">{t('oauthDescription')}</p>

        {isOauthLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-32 rounded-xl bg-muted animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {SUPPORTED_INTEGRATIONS.map((plat) => {
              const active = oauthCreds.find((c) => c.issuer === plat.id);
              const desc = locale === 'zh' ? plat.descZh : plat.desc;

              // Compute the 4 states: connected, expiring (<= 7 days), expired, missing
              let state: 'connected' | 'expiring' | 'expired' | 'missing' = 'missing';
              let daysLeft = 0;

              if (active) {
                if (active.connected) {
                  if (active.expires_at) {
                    const nowSec = Date.now() / 1000;
                    if (active.expires_at < nowSec) {
                      state = 'expired';
                    } else if (active.expires_at < nowSec + 7 * 86400) {
                      state = 'expiring';
                      daysLeft = Math.max(1, Math.ceil((active.expires_at - nowSec) / 86400));
                    } else {
                      state = 'connected';
                    }
                  } else {
                    state = 'connected';
                  }
                } else {
                  state = 'missing';
                }
              }

              // Determine state colors and labels
              let badgeColorClass = '';
              let badgePulseDotClass = '';
              let badgeText = '';

              if (state === 'connected') {
                badgeColorClass =
                  'bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/30';
                badgePulseDotClass = 'bg-emerald-500';
                badgeText = t('connected');
              } else if (state === 'expiring') {
                badgeColorClass =
                  'bg-amber-500/15 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 border border-amber-500/30';
                badgePulseDotClass = 'bg-amber-500';
                badgeText = t('expiringSoon', { days: daysLeft });
              } else if (state === 'expired') {
                badgeColorClass = 'bg-red-500/15 text-red-500 hover:bg-red-500/20 border border-red-500/30';
                badgePulseDotClass = 'bg-red-500';
                badgeText = t('expired');
              } else {
                badgeColorClass = 'bg-muted text-muted-foreground';
                badgeText = t('disconnected');
              }

              return (
                <div
                  key={plat.id}
                  className={cn(
                    'flex flex-col justify-between p-5 rounded-xl border transition-all duration-200 hover:shadow-md bg-card/50',
                    state === 'connected'
                      ? 'border-emerald-500/20'
                      : state === 'expiring'
                        ? 'border-amber-500/30'
                        : state === 'expired'
                          ? 'border-red-500/30 bg-red-500/5'
                          : 'border-border',
                  )}
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <div className="font-semibold text-base text-foreground">{plat.name}</div>
                      <Badge
                        variant={active ? 'default' : 'secondary'}
                        className={cn('px-2.5 py-0.5 rounded-full text-xs font-medium', badgeColorClass)}
                      >
                        <div className="flex items-center gap-1.5">
                          {state !== 'missing' && (
                            <span className={cn('h-1.5 w-1.5 rounded-full animate-pulse', badgePulseDotClass)} />
                          )}
                          {badgeText}
                        </div>
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{desc}</p>

                    {state === 'expired' && (
                      <div className="mt-4 flex items-center gap-2.5 p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-600 dark:text-red-400 leading-relaxed animate-in fade-in-50 duration-200">
                        <IconAlertCircle className="w-4 h-4 flex-shrink-0 text-red-500" />
                        <div className="flex-1 font-medium">
                          {locale === 'zh'
                            ? '当前凭证已失效（可能在三方平台被吊销或到期）。请点击一键修复重新授权，以恢复该服务。'
                            : 'This authorization has invalidated (revoked or expired on the platform). Please click Fix Now to re-authorize.'}
                        </div>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => setConnectModalTarget(plat)}
                          className="h-7 px-2.5 text-xs font-semibold whitespace-nowrap bg-red-500 hover:bg-red-600 text-white flex-shrink-0 shadow-red-500/20"
                        >
                          {locale === 'zh' ? '一键修复' : 'Fix Now'}
                        </Button>
                      </div>
                    )}

                    {active && state !== 'expired' && (
                      <div className="mt-4 space-y-1.5 bg-muted/30 rounded-lg p-3 text-xs border border-border/50">
                        {active.user_id && (
                          <div className="flex justify-between items-center">
                            <span className="text-muted-foreground">{t('userId')}:</span>
                            <span className="font-medium font-mono text-foreground">{active.user_id}</span>
                          </div>
                        )}
                        {active.scope && (
                          <div className="flex justify-between items-center">
                            <span className="text-muted-foreground">{t('scope')}:</span>
                            <span className="font-medium max-w-[180px] truncate text-foreground">{active.scope}</span>
                          </div>
                        )}
                        <div className="flex justify-between items-center">
                          <span className="text-muted-foreground">{t('expiresAt')}:</span>
                          <span className="font-medium text-foreground">
                            {active.expires_at
                              ? new Date(active.expires_at * 1000).toLocaleString()
                              : t('neverExpires')}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="mt-5 flex justify-end">
                    {active ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={async () => {
                          setDisconnectConfirmTarget(plat);
                          try {
                            const count = await countProviderTrees(plat.id);
                            setProviderTreeCount(count);
                          } catch {
                            setProviderTreeCount(0);
                          }
                        }}
                        className="text-red-500 border-red-500/30 hover:border-red-500 hover:bg-red-500/10"
                      >
                        {t('disconnect')}
                      </Button>
                    ) : (
                      <Button size="sm" variant="default" onClick={() => setConnectModalTarget(plat)}>
                        {t('connect')}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t('deleteConfirmTitle', { defaultValue: 'Delete Credential' })}
        description={t('deleteConfirmDesc', {
          defaultValue: `Are you sure you want to delete "${deleteTarget}"? This action cannot be undone.`,
        })}
        confirmText={t('deleteConfirmBtn', { defaultValue: 'Delete' })}
        cancelText={t('deleteCancel', { defaultValue: 'Cancel' })}
        variant="destructive"
        onConfirm={handleDeleteConfirm}
      />

      <ConfirmDialog
        open={!!deleteVaultTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteVaultTarget(null);
        }}
        title="Delete Vault Credential"
        description={`Are you sure you want to delete the credential "${deleteVaultTarget}"? This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        variant="destructive"
        onConfirm={handleDeleteVaultConfirm}
      />

      {/* Vault Credential Modal */}
      {vaultModalOpen && (
        <Dialog
          open={vaultModalOpen}
          onOpenChange={(open) => {
            if (!open) {
              setVaultModalOpen(false);
            }
          }}
        >
          <DialogContent className="sm:max-w-md bg-card border border-border">
            <DialogHeader>
              <DialogTitle className="text-foreground">
                {editingVaultCred ? 'Edit Vault Credential' : 'Add Vault Credential'}
              </DialogTitle>
              <DialogDescription className="text-muted-foreground">
                Store passwords and TOTP seeds securely. They will never be exposed to the LLM context.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="vaultLabel" className="text-foreground">
                  Label (Unique ID for LLM to use)
                </Label>
                <Input
                  id="vaultLabel"
                  type="text"
                  placeholder="e.g. github-personal"
                  value={vaultLabel}
                  onChange={(e) => setVaultLabel(e.target.value)}
                  disabled={!!editingVaultCred}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="vaultPassword" className="text-foreground">
                  Password {editingVaultCred && '(Leave blank to keep existing)'}
                </Label>
                <Input
                  id="vaultPassword"
                  type="password"
                  placeholder="Enter password"
                  value={vaultPassword}
                  onChange={(e) => setVaultPassword(e.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="vaultTotp" className="text-foreground">
                  TOTP Seed {editingVaultCred && '(Leave blank to keep existing)'}
                </Label>
                <Input
                  id="vaultTotp"
                  type="password"
                  placeholder="e.g. JBSWY3DPEHPK3PXP"
                  value={vaultTotp}
                  onChange={(e) => setVaultTotp(e.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="vaultDesc" className="text-foreground">
                  Description (Optional)
                </Label>
                <Input
                  id="vaultDesc"
                  type="text"
                  placeholder="What is this credential for?"
                  value={vaultDesc}
                  onChange={(e) => setVaultDesc(e.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setVaultModalOpen(false)}
              >
                Cancel
              </Button>
              <Button onClick={handleSaveVaultCredential}>Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Disconnect OAuth Confirm Dialog */}
      {disconnectConfirmTarget && (
        <Dialog
          open={!!disconnectConfirmTarget}
          onOpenChange={(open) => {
            if (!open) {
              setDisconnectConfirmTarget(null);
              setClearSyncedMemory(false);
            }
          }}
        >
          <DialogContent className="sm:max-w-md bg-card border border-border">
            <DialogHeader>
              <DialogTitle className="text-foreground">
                {t('disconnectConfirmTitle', { name: disconnectConfirmTarget.name })}
              </DialogTitle>
              <DialogDescription className="text-muted-foreground">
                {t('disconnectConfirmDesc', { name: disconnectConfirmTarget.name })}
              </DialogDescription>
            </DialogHeader>

            {providerTreeCount > 0 && (
              <div className="flex items-start gap-3 py-2">
                <Checkbox
                  id="clear-synced-memory"
                  checked={clearSyncedMemory}
                  onCheckedChange={(checked) => setClearSyncedMemory(checked === true)}
                />
                <label
                  htmlFor="clear-synced-memory"
                  className="text-sm leading-relaxed cursor-pointer text-muted-foreground"
                >
                  {locale === 'zh'
                    ? `同时清除已同步的记忆数据（${providerTreeCount} 个数据源）`
                    : `Also remove synced memory data (${providerTreeCount} source${providerTreeCount > 1 ? 's' : ''})`}
                </label>
              </div>
            )}

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setDisconnectConfirmTarget(null);
                  setClearSyncedMemory(false);
                }}
              >
                {t('deleteCancel')}
              </Button>
              <Button variant="destructive" onClick={handleDisconnectOauth}>
                {t('disconnect')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Connect Integration Modal */}
      {connectModalTarget && (
        <Dialog
          open={!!connectModalTarget}
          onOpenChange={(open) => {
            if (!open) {
              setConnectModalTarget(null);
              setTokenInput('');
              setUserIdInput('');
              setScopeInput('');
            }
          }}
        >
          <DialogContent className="sm:max-w-md bg-card border border-border">
            <DialogHeader>
              <DialogTitle className="text-foreground">
                {t('connectTitle', { name: connectModalTarget.name })}
              </DialogTitle>
              <DialogDescription className="text-muted-foreground">
                {t('connectDesc', { name: connectModalTarget.name })}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="token" className="text-foreground">
                  {t('tokenLabel')}
                </Label>
                <Input
                  id="token"
                  type="password"
                  placeholder={t('tokenPlaceholder')}
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground focus:ring-primary focus:border-primary"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="userId" className="text-foreground">
                  {t('userIdLabel')}
                </Label>
                <Input
                  id="userId"
                  type="text"
                  placeholder={t('userIdPlaceholder')}
                  value={userIdInput}
                  onChange={(e) => setUserIdInput(e.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="scope" className="text-foreground">
                  {t('scopeLabel')}
                </Label>
                <Input
                  id="scope"
                  type="text"
                  placeholder={t('scopePlaceholder')}
                  value={scopeInput}
                  onChange={(e) => setScopeInput(e.target.value)}
                  className="bg-muted border border-border text-foreground placeholder:text-muted-foreground"
                />
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setConnectModalTarget(null);
                  setTokenInput('');
                  setUserIdInput('');
                  setScopeInput('');
                }}
              >
                {t('deleteCancel')}
              </Button>
              <Button onClick={handleConnectOauth}>{t('saveBtn')}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </SettingsSection>,
    locale,
  );
});

CredentialsSection.displayName = 'CredentialsSection';

export default CredentialsSection;
