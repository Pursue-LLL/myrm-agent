'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconLock, IconCopy, IconCheck } from '@/components/ui/icons/PremiumIcons';
import { toast } from '@/lib/utils/toast';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import {
  changeWebuiPassword,
  disableWebuiProtection,
  fetchWebuiProtection,
  generateWebuiSetupToken,
} from '@/services/webui-auth';

const WebuiAccessSecurityPanel = memo(() => {
  const t = useTranslations('settings.system.webuiAccess');
  const [adminConfigured, setAdminConfigured] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const cfg = await fetchWebuiProtection();
      setAdminConfigured(cfg.admin_configured);
    } catch {
      setAdminConfigured(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast.error(t('passwordMismatch'));
      return;
    }
    setBusy(true);
    try {
      await changeWebuiPassword(currentPassword, newPassword);
      toast.success(t('passwordChanged'));
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('passwordChangeFailed'));
    } finally {
      setBusy(false);
    }
  };

  const handleDisableProtection = async () => {
    if (!currentPassword) {
      toast.error(t('currentPasswordRequired'));
      return;
    }
    setBusy(true);
    try {
      await disableWebuiProtection(currentPassword);
      toast.success(t('protectionDisabled'));
      setCurrentPassword('');
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('disableFailed'));
    } finally {
      setBusy(false);
    }
  };

  const handleCopySetupLink = async () => {
    setBusy(true);
    try {
      const { setup_path } = await generateWebuiSetupToken();
      const url = `${window.location.origin}${setup_path}`;
      await writeToClipboard(url);
      setCopied(true);
      toast.success(t('setupLinkCopied'));
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('setupLinkFailed'));
    } finally {
      setBusy(false);
    }
  };

  if (!adminConfigured) {
    return (
      <div className="p-4 rounded-xl bg-muted/30 border border-border space-y-2">
        <p className="text-xs text-muted-foreground leading-relaxed">{t('notConfiguredHint')}</p>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleCopySetupLink()}
          className="px-4 py-2 bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground rounded-lg text-xs font-bold"
        >
          {copied ? <IconCheck className="w-4 h-4 inline mr-1" /> : <IconCopy className="w-4 h-4 inline mr-1" />}
          {t('copySetupLink')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4 rounded-xl bg-muted/30 border border-border">
      <div className="flex items-center gap-2">
        <IconLock className="w-4 h-4 text-muted-foreground" />
        <h3 className="text-sm font-bold text-foreground">{t('title')}</h3>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{t('description')}</p>

      <div className="space-y-2">
        <label className="text-xs font-medium text-foreground">{t('currentPassword')}</label>
        <input
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm"
          autoComplete="current-password"
        />
      </div>
      <div className="space-y-2">
        <label className="text-xs font-medium text-foreground">{t('newPassword')}</label>
        <input
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm"
          autoComplete="new-password"
        />
      </div>
      <div className="space-y-2">
        <label className="text-xs font-medium text-foreground">{t('confirmPassword')}</label>
        <input
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm"
          autoComplete="new-password"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || !currentPassword || !newPassword}
          onClick={() => void handleChangePassword()}
          className="px-4 py-2 bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground rounded-lg text-xs font-bold"
        >
          {t('changePassword')}
        </button>
        <button
          type="button"
          disabled={busy || !currentPassword}
          onClick={() => void handleDisableProtection()}
          className="px-4 py-2 bg-muted hover:bg-muted/80 disabled:opacity-50 rounded-lg text-xs font-bold"
        >
          {t('disableProtection')}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleCopySetupLink()}
          className="px-4 py-2 bg-muted hover:bg-muted/80 disabled:opacity-50 rounded-lg text-xs font-bold"
        >
          {t('copySetupLink')}
        </button>
      </div>
    </div>
  );
});

WebuiAccessSecurityPanel.displayName = 'WebuiAccessSecurityPanel';

export default WebuiAccessSecurityPanel;
