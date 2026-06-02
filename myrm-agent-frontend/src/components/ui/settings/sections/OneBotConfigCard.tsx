'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { IconEye, IconEyeOff, IconLoader, IconWifi } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { OneBotCredentials } from '@/services/channels';
import { getOneBotCredentials, saveOneBotCredentials, testOneBotConnection } from '@/services/channels';
import { ConnectionBadge } from './ConnectionBadge';
import { useChannelConfig } from './useChannelConfig';

const EMPTY_CREDS: OneBotCredentials = { host: '0.0.0.0', port: '3001', accessToken: '' };

interface OneBotConfig {
  groupPolicy: 'open' | 'disabled' | 'allowlist';
  groupTrigger: 'mention_only' | 'prefix' | 'all';
  dmPolicy: 'open' | 'pairing' | 'allowlist' | 'disabled';
  triggerPrefixes?: string[]; // Used when groupTrigger is 'prefix'
}

const DEFAULT_CONFIG: OneBotConfig = {
  groupPolicy: 'open',
  groupTrigger: 'mention_only',
  dmPolicy: 'open',
};

export function OneBotConfigCard() {
  const t = useTranslations('channels');
  const [showToken, setShowToken] = useState(false);
  const [config, setConfig] = useState<OneBotConfig>(DEFAULT_CONFIG);
  const [configDirty, setConfigDirty] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  const { creds, dirty, loading, saving, testing, connStatus, statusLabel, handleChange, handleSave, handleTest } =
    useChannelConfig<OneBotCredentials>({
      emptyCreds: EMPTY_CREDS,
      requiredFields: ['host', 'port'],
      getCreds: getOneBotCredentials,
      saveCreds: saveOneBotCredentials,
      testConnection: (c) => testOneBotConnection(c.host, c.port, c.accessToken),
      i18nPrefix: 'onebot',
    });

  useEffect(() => {
    async function loadConfig() {
      try {
        const response = await fetch('/api/v1/channels/manage/onebot/config');
        if (response.ok) {
          const data = await response.json();
          setConfig({
            groupPolicy: data.groupPolicy || 'open',
            groupTrigger: data.groupTrigger || 'mention_only',
            dmPolicy: data.dmPolicy || 'open',
            triggerPrefixes: data.triggerPrefixes || [],
          });
        }
      } catch (error) {
        console.error('Failed to load OneBot config:', error);
      }
    }
    loadConfig();
  }, []);

  const handleConfigChange = <K extends keyof OneBotConfig>(key: K, value: OneBotConfig[K]) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    setConfigDirty(true);
  };

  const handleSaveConfig = async () => {
    setSavingConfig(true);
    try {
      const response = await fetch('/api/v1/channels/manage/onebot/config', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (response.ok) {
        setConfigDirty(false);
      }
    } catch (error) {
      console.error('Failed to save OneBot config:', error);
    } finally {
      setSavingConfig(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ConnectionBadge status={connStatus} label={statusLabel} />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="onebot-host">{t('onebotHost')}</Label>
          <Input
            id="onebot-host"
            placeholder="0.0.0.0"
            value={creds.host}
            onChange={(e) => handleChange('host', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="onebot-port">{t('onebotPort')}</Label>
          <Input
            id="onebot-port"
            placeholder="3001"
            value={creds.port}
            onChange={(e) => handleChange('port', e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="onebot-token">
          {t('onebotAccessToken')} <span className="text-muted-foreground font-normal">({t('optional')})</span>
        </Label>
        <div className="relative">
          <Input
            id="onebot-token"
            type={showToken ? 'text' : 'password'}
            placeholder="Your secret token"
            value={creds.accessToken}
            onChange={(e) => handleChange('accessToken', e.target.value)}
            className="pr-10"
          />
          <button
            type="button"
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
            onClick={() => setShowToken(!showToken)}
          >
            {showToken ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">{t('onebotHint')}</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving || !dirty} size="sm">
          {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
          {t('onebotSave')}
        </Button>
        <Button variant="outline" onClick={handleTest} disabled={testing || !creds.host || !creds.port} size="sm">
          {testing ? (
            <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <IconWifi className="mr-2 h-3.5 w-3.5" />
          )}
          {t('onebotTestConnection')}
        </Button>
      </div>

      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium mb-3">{t('onebotAdvancedSettings')}</h4>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>{t('onebotGroupPolicy')}</Label>
            <select
              className="w-full px-3 py-2 border rounded-full bg-background"
              value={config.groupPolicy}
              onChange={(e) => handleConfigChange('groupPolicy', e.target.value as 'open' | 'disabled' | 'allowlist')}
            >
              <option value="open">{t('onebotGroupPolicyOpen')}</option>
              <option value="disabled">{t('onebotGroupPolicyDisabled')}</option>
              <option value="allowlist">{t('onebotGroupPolicyAllowlist')}</option>
            </select>
            <p className="text-xs text-muted-foreground">{t('onebotGroupPolicyHint')}</p>
          </div>
          <div className="space-y-2">
            <Label>{t('onebotGroupTrigger')}</Label>
            <select
              className="w-full px-3 py-2 border rounded-full bg-background"
              value={config.groupTrigger}
              onChange={(e) => handleConfigChange('groupTrigger', e.target.value as 'mention_only' | 'prefix' | 'all')}
            >
              <option value="mention_only">{t('onebotTriggerMention')}</option>
              <option value="prefix">{t('onebotTriggerPrefix')}</option>
              <option value="all">{t('onebotTriggerAll')}</option>
            </select>
            <p className="text-xs text-muted-foreground">{t('onebotTriggerHint')}</p>
          </div>
          <div className="space-y-2">
            <Label>{t('onebotDmPolicy')}</Label>
            <select
              className="w-full px-3 py-2 border rounded-full bg-background"
              value={config.dmPolicy}
              onChange={(e) =>
                handleConfigChange('dmPolicy', e.target.value as 'open' | 'pairing' | 'allowlist' | 'disabled')
              }
            >
              <option value="open">{t('onebotDmOpen')}</option>
              <option value="pairing">{t('onebotDmPairing')}</option>
              <option value="allowlist">{t('onebotDmAllowlist')}</option>
              <option value="disabled">{t('onebotDmDisabled')}</option>
            </select>
            <p className="text-xs text-muted-foreground">{t('onebotDmHint')}</p>
          </div>
          <Button onClick={handleSaveConfig} disabled={savingConfig || !configDirty} size="sm">
            {savingConfig && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
            {t('onebotSaveConfig')}
          </Button>
        </div>
      </div>
    </div>
  );
}
