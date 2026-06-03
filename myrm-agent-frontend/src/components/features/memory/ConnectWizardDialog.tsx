'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, Copy, Link2, RefreshCw, Unlink, Zap } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { Checkbox } from '@/components/primitives/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import {
  type ConnectProfile,
  type GenerateConfigResponse,
  fetchConnectProfiles,
  generateConnectConfig,
  revokeConnect,
  runConnectDoctor,
} from '@/services/connect';
import { countProviderTrees } from '@/services/integrationMemory';
import { cn } from '@/lib/utils/classnameUtils';

interface ConnectWizardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type WizardStep = 'select' | 'config' | 'done';

export function ConnectWizardDialog({ open, onOpenChange }: ConnectWizardDialogProps) {
  const t = useTranslations('connectWizard');
  const [step, setStep] = useState<WizardStep>('select');
  const [profiles, setProfiles] = useState<ConnectProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [configResult, setConfigResult] = useState<GenerateConfigResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);
  const [doctorResult, setDoctorResult] = useState<boolean | null>(null);
  const [doctorRunning, setDoctorRunning] = useState(false);

  const loadProfiles = useCallback(async () => {
    try {
      const data = await fetchConnectProfiles();
      setProfiles(data);
    } catch {
      // Silently handle - profiles will be empty
    }
  }, []);

  const handleOpen = useCallback(
    (isOpen: boolean) => {
      if (isOpen) {
        setStep('select');
        setSelectedProfile(null);
        setConfigResult(null);
        setCopiedConfig(false);
        setCopiedToken(false);
        setDoctorResult(null);
        loadProfiles();
      }
      onOpenChange(isOpen);
    },
    [onOpenChange, loadProfiles],
  );

  const handleGenerate = useCallback(async () => {
    if (!selectedProfile) return;
    setLoading(true);
    try {
      const result = await generateConnectConfig(selectedProfile);
      setConfigResult(result);
      setStep('config');
    } catch {
      // Error handled by apiRequest globally
    } finally {
      setLoading(false);
    }
  }, [selectedProfile]);

  const handleCopyConfig = useCallback(async () => {
    if (!configResult) return;
    const configJson = configResult.config_json;
    const text = (configJson as Record<string, unknown>)._toml_snippet
      ? String((configJson as Record<string, unknown>)._toml_snippet)
      : JSON.stringify(configJson, null, 2);
    await navigator.clipboard.writeText(text);
    setCopiedConfig(true);
    setTimeout(() => setCopiedConfig(false), 2000);
  }, [configResult]);

  const handleCopyToken = useCallback(async () => {
    if (!configResult) return;
    await navigator.clipboard.writeText(configResult.token);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  }, [configResult]);

  const handleDoctor = useCallback(async () => {
    if (!selectedProfile) return;
    setDoctorRunning(true);
    try {
      const result = await runConnectDoctor(selectedProfile);
      setDoctorResult(result.healthy);
    } catch {
      setDoctorResult(false);
    } finally {
      setDoctorRunning(false);
    }
  }, [selectedProfile]);

  const [revokeConfirming, setRevokeConfirming] = useState(false);
  const [clearSyncedMemory, setClearSyncedMemory] = useState(false);
  const [providerTreeCount, setProviderTreeCount] = useState(0);

  const handleRevoke = useCallback(async () => {
    if (!selectedProfile) return;
    if (!revokeConfirming) {
      setRevokeConfirming(true);
      countProviderTrees(selectedProfile)
        .then((count) => setProviderTreeCount(count))
        .catch(() => setProviderTreeCount(0));
      return;
    }
    setRevokeConfirming(false);
    try {
      await revokeConnect(selectedProfile, clearSyncedMemory);
      setClearSyncedMemory(false);
      setStep('select');
      setConfigResult(null);
      setDoctorResult(null);
      loadProfiles();
    } catch {
      // Error handled globally
    }
  }, [selectedProfile, revokeConfirming, clearSyncedMemory, loadProfiles]);

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5 text-primary" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        {step === 'select' && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">{t('selectAgentDesc')}</p>
            <div className="space-y-2">
              {profiles.map((profile) => (
                <button
                  key={profile.id}
                  type="button"
                  onClick={() => setSelectedProfile(profile.id)}
                  className={cn(
                    'w-full rounded-lg border p-3 text-left transition-colors',
                    selectedProfile === profile.id
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/50 hover:bg-accent/30',
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{profile.label}</span>
                    <StatusBadge status={profile.status} t={t} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{profile.description}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground/70">
                    {t('configFile')}: <code className="text-[10px]">{profile.config_file_path}</code>
                  </p>
                </button>
              ))}
            </div>
            <Button onClick={handleGenerate} disabled={!selectedProfile || loading} className="w-full">
              <Zap className="mr-2 h-4 w-4" />
              {loading ? t('generating') : t('generate')}
            </Button>
          </div>
        )}

        {step === 'config' && configResult && (
          <div className="space-y-4">
            <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3">
              <p className="text-sm font-medium text-green-700 dark:text-green-400">{t('configReady')}</p>
              <p className="text-xs text-muted-foreground mt-1">{configResult.instructions}</p>
            </div>

            <div className="space-y-2">
              <div className="relative">
                <pre className="rounded-full bg-muted p-3 text-xs overflow-x-auto max-h-40">
                  {(configResult.config_json as Record<string, unknown>)._toml_snippet
                    ? String((configResult.config_json as Record<string, unknown>)._toml_snippet)
                    : JSON.stringify(configResult.config_json, null, 2)}
                </pre>
                <Button
                  variant="ghost"
                  size="sm"
                  className="absolute top-1 right-1 h-7 px-2"
                  onClick={handleCopyConfig}
                >
                  {copiedConfig ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  <span className="ml-1 text-xs">{copiedConfig ? t('copied') : t('copyConfig')}</span>
                </Button>
              </div>

              <div className="rounded-full border border-amber-500/20 bg-amber-500/5 p-2">
                <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
                  {t('token')}: <code className="text-[10px] break-all">{configResult.token}</code>
                </p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-[10px] text-amber-600/70 dark:text-amber-400/70">{t('tokenWarning')}</p>
                  <Button variant="ghost" size="sm" className="h-6 px-2" onClick={handleCopyToken}>
                    <Copy className="h-3 w-3 mr-1" />
                    <span className="text-[10px]">{copiedToken ? t('copied') : t('copy')}</span>
                  </Button>
                </div>
              </div>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={handleDoctor} disabled={doctorRunning}>
                <RefreshCw className={cn('mr-2 h-4 w-4', doctorRunning && 'animate-spin')} />
                {doctorRunning ? t('doctorRunning') : t('doctor')}
              </Button>
              <Button variant="destructive" size="sm" onClick={handleRevoke}>
                <Unlink className="mr-1 h-3.5 w-3.5" />
                {revokeConfirming ? t('revokeConfirm') : t('revoke')}
              </Button>
            </div>

            {revokeConfirming && providerTreeCount > 0 && (
              <div className="flex items-start gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                <Checkbox
                  id="revoke-clear-memory"
                  checked={clearSyncedMemory}
                  onCheckedChange={(checked) => setClearSyncedMemory(checked === true)}
                />
                <label
                  htmlFor="revoke-clear-memory"
                  className="text-xs leading-relaxed cursor-pointer text-muted-foreground"
                >
                  {t('clearSyncedMemory', {
                    count: providerTreeCount,
                    defaultMessage: `Also remove synced memory data (${providerTreeCount} source${providerTreeCount > 1 ? 's' : ''})`,
                  })}
                </label>
              </div>
            )}

            {doctorResult !== null && (
              <div
                className={cn(
                  'rounded-full p-2 text-xs',
                  doctorResult
                    ? 'bg-green-500/10 text-green-700 dark:text-green-400'
                    : 'bg-red-500/10 text-red-700 dark:text-red-400',
                )}
              >
                {doctorResult ? t('doctorHealthy') : t('doctorUnhealthy')}
              </div>
            )}

            <Button variant="ghost" className="w-full" onClick={() => handleOpen(false)}>
              {t('close')}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function StatusBadge({ status, t }: { status: string; t: ReturnType<typeof useTranslations> }) {
  const colorMap: Record<string, string> = {
    ready: 'bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20',
    manual_config_required: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20',
    missing: 'bg-muted text-muted-foreground border-border',
  };
  return (
    <span
      className={cn('rounded-full border px-2 py-0.5 text-[10px] font-medium', colorMap[status] || colorMap.missing)}
    >
      {t(`status.${status}` as Parameters<typeof t>[0])}
    </span>
  );
}
