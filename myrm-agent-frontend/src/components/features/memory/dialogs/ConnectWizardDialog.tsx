'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { CheckCircle2, Copy, Download, FileJson, Link2, Package, RefreshCw, Unlink, Zap } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { Checkbox } from '@/components/primitives/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { toast } from '@/lib/utils/toast';
import {
  AGENT_PLUGIN_PROFILE_ID,
  type AgentPluginBundleResponse,
  type ConnectProfile,
  type GenerateConfigResponse,
  listConnectProfiles,
  generateConnectConfig,
  generateAgentPluginBundle,
  revokeConnect,
  runConnectDoctor,
} from '@/services/connect';
import { listAgents, type AgentListItem } from '@/services/agent';
import { countProviderTrees } from '@/services/memory/integration';
import { getFileExtension, getMimeType, triggerDownload, buildZipFromFiles, sanitizeFilename } from '@/lib/utils/fileUtils';
import { resolveDoctorMessageKey, resolveDoctorSeverity, type DoctorSeverity } from '@/lib/i18n/connectDoctor';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { cn } from '@/lib/utils/classnameUtils';

interface ConnectWizardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type WizardStep = 'select' | 'config' | 'plugin' | 'done';

interface DoctorOutcome {
  healthy: boolean;
  detail: string;
  severity?: DoctorSeverity;
}

const DOCTOR_BOX_CLASSES: Record<DoctorSeverity, string> = {
  ok: 'border-green-500/20 bg-green-500/10 text-green-700 dark:text-green-400',
  warn: 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  error: 'border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-400',
};

export function ConnectWizardDialog({ open, onOpenChange }: ConnectWizardDialogProps) {
  const locale = useLocale();
  const t = useTranslations('connectWizard');
  const [step, setStep] = useState<WizardStep>('select');
  const [profiles, setProfiles] = useState<ConnectProfile[]>([]);
  const [agents, setAgents] = useState<AgentListItem[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState('default');
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [configResult, setConfigResult] = useState<GenerateConfigResponse | null>(null);
  const [pluginResult, setPluginResult] = useState<AgentPluginBundleResponse | null>(null);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);
  const [copiedFile, setCopiedFile] = useState(false);
  const [pluginEmbedToken, setPluginEmbedToken] = useState(false);
  const [doctorResult, setDoctorResult] = useState<DoctorOutcome | null>(null);
  const [doctorRunning, setDoctorRunning] = useState(false);

  const loadProfiles = useCallback(async () => {
    try {
      const data = await listConnectProfiles();
      setProfiles(data);
    } catch {
      // Silently handle - profiles will be empty
    }
  }, []);

  const loadAgents = useCallback(async () => {
    try {
      const response = await listAgents(1, 100);
      setAgents(response.items ?? []);
    } catch {
      setAgents([]);
    }
  }, []);

  useEffect(() => {
    if (agents.length === 0) {
      return;
    }
    if (!agents.some((agent) => agent.id === selectedAgentId)) {
      setSelectedAgentId(agents[0]?.id ?? 'default');
    }
  }, [agents, selectedAgentId]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setStep('select');
    setSelectedAgentId('default');
    setSelectedProfile(null);
    setConfigResult(null);
    setPluginResult(null);
    setSelectedFile('');
    setPluginEmbedToken(false);
    setCopiedConfig(false);
    setCopiedToken(false);
    setCopiedFile(false);
    setDoctorResult(null);
    setRevokeConfirming(false);
    setClearSyncedMemory(false);
    setDownloadingBundle(false);
    void loadAgents();
    loadProfiles();
  }, [open, loadProfiles, loadAgents]);

  const handleOpen = useCallback(
    (isOpen: boolean) => {
      onOpenChange(isOpen);
    },
    [onOpenChange],
  );

  const handleGenerate = useCallback(async () => {
    if (!selectedProfile) {return;}
    setLoading(true);
    try {
      const result = await generateConnectConfig(selectedProfile, selectedAgentId);
      setConfigResult(result);
      setStep('config');
    } catch {
      // Error handled by apiRequest globally
    } finally {
      setLoading(false);
    }
  }, [selectedProfile, selectedAgentId]);

  const handleCopyConfig = useCallback(async () => {
    if (!configResult) {return;}
    const configJson = configResult.config_json;
    const text = (configJson as Record<string, unknown>)._toml_snippet
      ? String((configJson as Record<string, unknown>)._toml_snippet)
      : JSON.stringify(configJson, null, 2);
    await navigator.clipboard.writeText(text);
    setCopiedConfig(true);
    setTimeout(() => setCopiedConfig(false), 2000);
  }, [configResult]);

  const handleCopyToken = useCallback(async () => {
    if (!configResult) {return;}
    await navigator.clipboard.writeText(configResult.token);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  }, [configResult]);

  const handleGeneratePlugin = useCallback(async () => {
    setLoading(true);
    try {
      const result = await generateAgentPluginBundle(selectedAgentId, pluginEmbedToken);
      setPluginResult(result);
      setSelectedFile(Object.keys(result.files)[0] ?? '');
      setStep('plugin');
    } catch {
      // Error handled by apiRequest globally
    } finally {
      setLoading(false);
    }
  }, [selectedAgentId, pluginEmbedToken]);

  const handleCopyPluginFile = useCallback(async () => {
    if (!pluginResult || !selectedFile) {return;}
    await navigator.clipboard.writeText(pluginResult.files[selectedFile] ?? '');
    setCopiedFile(true);
    setTimeout(() => setCopiedFile(false), 2000);
  }, [pluginResult, selectedFile]);

  const handleDownloadPluginFile = useCallback(
    async () => {
      if (!pluginResult || !selectedFile) {return;}
      const content = pluginResult.files[selectedFile] ?? '';
      if (!content) {return;}
      const filename = selectedFile.split('/').pop() ?? selectedFile;
      try {
        await triggerDownload(new Blob([content], { type: getMimeType(getFileExtension(filename)) }), filename);
      } catch (err) {
        console.error('[ConnectWizard] plugin file download failed:', err);
      }
    },
    [pluginResult, selectedFile],
  );

  const [downloadingBundle, setDownloadingBundle] = useState(false);

  const handleDownloadPluginBundle = useCallback(async () => {
    if (!pluginResult || downloadingBundle) {return;}
    setDownloadingBundle(true);
    try {
      const blob = await buildZipFromFiles(pluginResult.files);
      const agentName = agents.find((agent) => agent.id === pluginResult.agent_id)?.name;
      const safeAgentName = agentName ? sanitizeFilename(agentName).slice(0, 64) : '';
      const zipName = safeAgentName ? `myrm-memory-${safeAgentName}.zip` : 'myrm-memory.zip';
      await triggerDownload(blob, zipName);
    } catch {
      toast.error(t('downloadBundleFailed'));
    } finally {
      setDownloadingBundle(false);
    }
  }, [pluginResult, agents, downloadingBundle, t]);

  const handleCopyPluginToken = useCallback(async () => {
    if (!pluginResult) {return;}
    await navigator.clipboard.writeText(pluginResult.token);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  }, [pluginResult]);

  const handleDoctorPlugin = useCallback(async () => {
    setDoctorRunning(true);
    try {
      const result = await runConnectDoctor(AGENT_PLUGIN_PROFILE_ID);
      setDoctorResult({ healthy: result.healthy, detail: result.detail, severity: result.severity });
    } catch {
      setDoctorResult({ healthy: false, detail: 'unknown' });
    } finally {
      setDoctorRunning(false);
    }
  }, []);

  const handleDoctor = useCallback(async () => {
    if (!selectedProfile) {return;}
    setDoctorRunning(true);
    try {
      const result = await runConnectDoctor(selectedProfile);
      setDoctorResult({ healthy: result.healthy, detail: result.detail, severity: result.severity });
    } catch {
      setDoctorResult({ healthy: false, detail: 'unknown' });
    } finally {
      setDoctorRunning(false);
    }
  }, [selectedProfile]);

  const [revokeConfirming, setRevokeConfirming] = useState(false);
  const [clearSyncedMemory, setClearSyncedMemory] = useState(false);
  const [providerTreeCount, setProviderTreeCount] = useState(0);

  const handleRevokePlugin = useCallback(async () => {
    if (!revokeConfirming) {
      setRevokeConfirming(true);
      return;
    }
    setRevokeConfirming(false);
    try {
      await revokeConnect(AGENT_PLUGIN_PROFILE_ID);
      setStep('select');
      setPluginResult(null);
      setSelectedFile('');
      setDoctorResult(null);
    } catch {
      // Error handled globally
    }
  }, [revokeConfirming]);

  const handleRevoke = useCallback(async () => {
    if (!selectedProfile) {return;}
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
            <div className="space-y-2">
              <p className="text-sm font-medium">{t('selectMyrmAgent')}</p>
              <p className="text-xs text-muted-foreground">{t('selectMyrmAgentDesc')}</p>
              <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
                <SelectTrigger>
                  <SelectValue placeholder={t('selectMyrmAgent')} />
                </SelectTrigger>
                <SelectContent>
                  {agents.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {getBuiltinAgentName(agent.id, agent.name || agent.id, locale)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">{t('selectExternalTool')}</p>
              <p className="text-xs text-muted-foreground">{t('selectAgentDesc')}</p>
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

            <div className="rounded-lg border border-dashed p-3 space-y-3">
              <div>
                <p className="text-sm font-medium flex items-center gap-1.5">
                  <Package className="h-4 w-4 text-primary" />
                  {t('agentPlugin')}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">{t('agentPluginDesc')}</p>
              </div>
              <div className="flex items-center justify-between gap-2">
                <label className="text-xs text-muted-foreground flex items-center gap-2 cursor-pointer">
                  <Switch checked={pluginEmbedToken} onCheckedChange={setPluginEmbedToken} />
                  {t('agentPluginEmbedToken')}
                </label>
              </div>
              <p className="text-[10px] text-muted-foreground/70">{t('agentPluginEmbedTokenHint')}</p>
              <Button onClick={handleGeneratePlugin} disabled={loading} className="w-full" variant="secondary">
                <FileJson className="mr-2 h-4 w-4" />
                {loading ? t('generating') : t('agentPluginGenerate')}
              </Button>
            </div>
          </div>
        )}

        {step === 'config' && configResult && (
          <div className="space-y-4">
            <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3">
              <p className="text-sm font-medium text-green-700 dark:text-green-400">{t('configReady')}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {t('memoryScopeAgent', {
                  agent: getBuiltinAgentName(
                    configResult.agent_id,
                    agents.find((agent) => agent.id === configResult.agent_id)?.name ?? configResult.agent_id,
                    locale,
                  ),
                })}
              </p>
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
                  'rounded-lg border p-3 text-xs leading-relaxed',
                  DOCTOR_BOX_CLASSES[
                    resolveDoctorSeverity(doctorResult.detail, doctorResult.healthy, doctorResult.severity)
                  ],
                )}
              >
                {t(resolveDoctorMessageKey(doctorResult.detail, doctorResult.healthy))}
              </div>
            )}

            <Button variant="ghost" className="w-full" onClick={() => handleOpen(false)}>
              {t('close')}
            </Button>
          </div>
        )}

        {step === 'plugin' && pluginResult && (
          <div className="space-y-4">
            <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3">
              <p className="text-sm font-medium text-green-700 dark:text-green-400">{t('agentPluginReady')}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {t('memoryScopeAgent', {
                  agent: getBuiltinAgentName(
                    pluginResult.agent_id,
                    agents.find((agent) => agent.id === pluginResult.agent_id)?.name ?? pluginResult.agent_id,
                    locale,
                  ),
                })}
              </p>
              <p className="text-xs text-muted-foreground mt-1">{pluginResult.instructions}</p>
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Select value={selectedFile} onValueChange={setSelectedFile}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder={t('pluginFile')} />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.keys(pluginResult.files).map((file) => (
                      <SelectItem key={file} value={file}>
                        {file}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button variant="ghost" size="sm" onClick={handleCopyPluginFile}>
                  {copiedFile ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  <span className="ml-1 text-xs">{copiedFile ? t('copied') : t('copy')}</span>
                </Button>
                <Button variant="ghost" size="sm" onClick={handleDownloadPluginFile}>
                  <Download className="h-3.5 w-3.5" />
                  <span className="ml-1 text-xs">{t('download')}</span>
                </Button>
              </div>
              <Button
                variant="secondary"
                className="w-full"
                onClick={handleDownloadPluginBundle}
                disabled={downloadingBundle}
              >
                <Download className="mr-2 h-4 w-4" />
                {downloadingBundle ? t('downloadingBundle') : t('downloadBundle')}
              </Button>
              <pre className="rounded-lg bg-muted p-3 text-xs overflow-x-auto max-h-48">
                {pluginResult.files[selectedFile] ?? ''}
              </pre>
            </div>

            <div className="rounded-full border border-amber-500/20 bg-amber-500/5 p-2">
              <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
                {t('token')}: <code className="text-[10px] break-all">{pluginResult.token}</code>
              </p>
              <div className="flex items-center justify-between mt-1">
                <p className="text-[10px] text-amber-600/70 dark:text-amber-400/70">{t('tokenWarning')}</p>
                <Button variant="ghost" size="sm" className="h-6 px-2" onClick={handleCopyPluginToken}>
                  <Copy className="h-3 w-3 mr-1" />
                  <span className="text-[10px]">{copiedToken ? t('copied') : t('copy')}</span>
                </Button>
              </div>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" className="flex-1" onClick={handleDoctorPlugin} disabled={doctorRunning}>
                <RefreshCw className={cn('mr-2 h-4 w-4', doctorRunning && 'animate-spin')} />
                {doctorRunning ? t('doctorRunning') : t('doctor')}
              </Button>
              <Button variant="destructive" size="sm" onClick={handleRevokePlugin}>
                <Unlink className="mr-1 h-3.5 w-3.5" />
                {revokeConfirming ? t('revokeConfirm') : t('revoke')}
              </Button>
            </div>

            {doctorResult !== null && (
              <div
                className={cn(
                  'rounded-lg border p-3 text-xs leading-relaxed',
                  DOCTOR_BOX_CLASSES[
                    resolveDoctorSeverity(doctorResult.detail, doctorResult.healthy, doctorResult.severity)
                  ],
                )}
              >
                {t(resolveDoctorMessageKey(doctorResult.detail, doctorResult.healthy))}
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
