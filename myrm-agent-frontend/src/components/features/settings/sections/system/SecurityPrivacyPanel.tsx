'use client';

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Navigation } from 'lucide-react';
import {
  IconShield,
  IconEye,
  IconEyeOff,
  IconBan,
  IconShieldAlert,
  IconRefresh,
  IconSearch,
  IconLoader,
  IconZap,
  IconAlertTriangle,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { toast } from '@/lib/utils/toast';
import { fetchWithTimeout } from '@/lib/api';
import useConfigStore from '@/store/useConfigStore';
import type { PIIAction, PrivacyS2Strategy, PrivacyS3Strategy, PrivacyLocalFallback } from '@/services/config/types';
import SettingsSection from '../SettingsSection';
import { AdvancedPiiConfig } from './AdvancedPiiConfig';

const SecurityPrivacyPanel = memo(() => {
  const t = useTranslations('settings.securityPolicy');
  const [testingLocalModel, setTestingLocalModel] = useState(false);

  const {
    privacyEnabled,
    privacyS2Action,
    privacyS3Action,
    privacyDeepScan,
    privacyRouting,
    setPrivacyEnabled,
    setPrivacyS2Action,
    setPrivacyS3Action,
    setPrivacyDeepScan,
    setPrivacyRouting,
  } = useConfigStore();

  const updateRoutingField = useCallback(
    (field: string, value: unknown) => {
      setPrivacyRouting({ ...privacyRouting, [field]: value });
    },
    [privacyRouting, setPrivacyRouting],
  );

  const handleTestLocalModel = useCallback(async () => {
    if (!privacyRouting?.localModel) return;
    setTestingLocalModel(true);
    try {
      const resp = await fetchWithTimeout(
        '/config/test-local-model',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: privacyRouting.localModel,
            base_url: privacyRouting.localBaseUrl || null,
            api_key: privacyRouting.localApiKey || null,
          }),
        },
        15000,
      );
      const data = await resp.json();
      if (data.success) {
        toast.success(`${t('privacy.routing.testSuccess')} (${data.latency_ms}ms)`);
      } else {
        toast.error(`${t('privacy.routing.testFailed')}: ${data.message}`);
      }
    } catch {
      toast.error(t('privacy.routing.testFailed'));
    } finally {
      setTestingLocalModel(false);
    }
  }, [privacyRouting, t]);

  return (
    <SettingsSection title={t('privacy.title')} description={t('privacy.description')}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <IconShield className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-medium text-foreground">{t('privacy.enableLabel')}</p>
              <p className="text-xs text-muted-foreground">{t('privacy.enableDesc')}</p>
            </div>
          </div>
          <Switch checked={privacyEnabled} onCheckedChange={setPrivacyEnabled} />
        </div>

        {privacyEnabled && (
          <div className="ml-11 space-y-3 pt-2 border-t border-border/50">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
              <div className="flex items-center gap-2 min-w-[180px]">
                <IconEye className="h-3.5 w-3.5 text-amber-500" />
                <span className="text-sm text-foreground">{t('privacy.s2Label')}</span>
              </div>
              <Select value={privacyS2Action} onValueChange={(v: string) => setPrivacyS2Action(v as PIIAction)}>
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="warn">
                    <span className="flex items-center gap-1.5">
                      <IconShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                      {t('privacy.actionWarn')}
                    </span>
                  </SelectItem>
                  <SelectItem value="pseudonymize">
                    <span className="flex items-center gap-1.5">
                      <IconRefresh className="h-3.5 w-3.5 text-emerald-500" />
                      {t('privacy.actionPseudonymize')}
                    </span>
                  </SelectItem>
                  <SelectItem value="redact">
                    <span className="flex items-center gap-1.5">
                      <IconEyeOff className="h-3.5 w-3.5 text-blue-500" />
                      {t('privacy.actionRedact')}
                    </span>
                  </SelectItem>
                  <SelectItem value="block">
                    <span className="flex items-center gap-1.5">
                      <IconBan className="h-3.5 w-3.5 text-destructive" />
                      {t('privacy.actionBlock')}
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
              <div className="flex items-center gap-2 min-w-[180px]">
                <IconEyeOff className="h-3.5 w-3.5 text-destructive" />
                <span className="text-sm text-foreground">{t('privacy.s3Label')}</span>
              </div>
              <Select value={privacyS3Action} onValueChange={(v: string) => setPrivacyS3Action(v as PIIAction)}>
                <SelectTrigger className="w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="warn">
                    <span className="flex items-center gap-1.5">
                      <IconShieldAlert className="h-3.5 w-3.5 text-amber-500" />
                      {t('privacy.actionWarn')}
                    </span>
                  </SelectItem>
                  <SelectItem value="pseudonymize">
                    <span className="flex items-center gap-1.5">
                      <IconRefresh className="h-3.5 w-3.5 text-emerald-500" />
                      {t('privacy.actionPseudonymize')}
                    </span>
                  </SelectItem>
                  <SelectItem value="redact">
                    <span className="flex items-center gap-1.5">
                      <IconEyeOff className="h-3.5 w-3.5 text-blue-500" />
                      {t('privacy.actionRedact')}
                    </span>
                  </SelectItem>
                  <SelectItem value="block">
                    <span className="flex items-center gap-1.5">
                      <IconBan className="h-3.5 w-3.5 text-destructive" />
                      {t('privacy.actionBlock')}
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {(privacyS2Action === 'pseudonymize' || privacyS3Action === 'pseudonymize') && (
              <div className="flex items-start gap-2 p-2.5 rounded-full bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/50">
                <IconRefresh className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                <p className="text-xs text-emerald-700 dark:text-emerald-400">{t('privacy.pseudonymizeHint')}</p>
              </div>
            )}

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <IconSearch className="h-3.5 w-3.5 text-primary" />
                <div>
                  <span className="text-sm text-foreground">{t('privacy.deepScanLabel')}</span>
                  <p className="text-xs text-muted-foreground">{t('privacy.deepScanDesc')}</p>
                </div>
              </div>
              <Switch checked={privacyDeepScan} onCheckedChange={setPrivacyDeepScan} />
            </div>

            <div className="mt-4 pt-4 border-t border-border/50 space-y-3">
              <div className="flex items-center gap-2 mb-2">
                <Navigation className="h-3.5 w-3.5 text-primary" />
                <span className="text-sm font-medium text-foreground">{t('privacy.routing.title')}</span>
              </div>
              <p className="text-xs text-muted-foreground mb-3">{t('privacy.routing.description')}</p>

              <div className="space-y-3">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-foreground">{t('privacy.routing.localModel')}</label>
                  <div className="flex items-center gap-2">
                    <Input
                      value={privacyRouting?.localModel ?? ''}
                      onChange={(e) => updateRoutingField('localModel', e.target.value || undefined)}
                      placeholder={t('privacy.routing.localModelPlaceholder')}
                      className="text-sm flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleTestLocalModel}
                      disabled={testingLocalModel || !privacyRouting?.localModel}
                      className="shrink-0"
                    >
                      {testingLocalModel ? (
                        <IconLoader className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                      ) : (
                        <IconZap className="w-3.5 h-3.5 mr-1.5" />
                      )}
                      {t('privacy.routing.testConnection')}
                    </Button>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-foreground">{t('privacy.routing.localBaseUrl')}</label>
                    <Input
                      value={privacyRouting?.localBaseUrl ?? ''}
                      onChange={(e) => updateRoutingField('localBaseUrl', e.target.value || undefined)}
                      placeholder={t('privacy.routing.localBaseUrlPlaceholder')}
                      className="text-sm"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-foreground">{t('privacy.routing.localApiKey')}</label>
                    <Input
                      type="password"
                      value={privacyRouting?.localApiKey ?? ''}
                      onChange={(e) => updateRoutingField('localApiKey', e.target.value || undefined)}
                      placeholder={t('privacy.routing.localApiKeyPlaceholder')}
                      className="text-sm"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-foreground">{t('privacy.routing.s2Strategy')}</label>
                    <Select
                      value={privacyRouting?.s2Strategy ?? 'cloud_after_redact'}
                      onValueChange={(v: string) => updateRoutingField('s2Strategy', v as PrivacyS2Strategy)}
                    >
                      <SelectTrigger className="text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cloud_after_redact">{t('privacy.routing.s2CloudAfterRedact')}</SelectItem>
                        <SelectItem value="local">{t('privacy.routing.s2Local')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-foreground">{t('privacy.routing.s3Strategy')}</label>
                    <Select
                      value={privacyRouting?.s3Strategy ?? 'local'}
                      onValueChange={(v: string) => updateRoutingField('s3Strategy', v as PrivacyS3Strategy)}
                    >
                      <SelectTrigger className="text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="local">{t('privacy.routing.s3Local')}</SelectItem>
                        <SelectItem value="block">{t('privacy.routing.s3Block')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-foreground">
                      {t('privacy.routing.localFallback')}
                    </label>
                    <Select
                      value={privacyRouting?.localFallback ?? 'block'}
                      onValueChange={(v: string) => updateRoutingField('localFallback', v as PrivacyLocalFallback)}
                    >
                      <SelectTrigger className="text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="block">{t('privacy.routing.fallbackBlock')}</SelectItem>
                        <SelectItem value="force_redact_cloud">
                          {t('privacy.routing.fallbackForceRedactCloud')}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {!privacyRouting?.localModel &&
                  (privacyRouting?.s2Strategy === 'local' || privacyRouting?.s3Strategy === 'local') && (
                    <div className="flex items-start gap-2 p-2.5 rounded-full bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50">
                      <IconAlertTriangle className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-amber-700 dark:text-amber-400">
                        {t('privacy.routing.noLocalModelWarning')}
                      </p>
                    </div>
                  )}
              </div>
            </div>

            <AdvancedPiiConfig />
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

SecurityPrivacyPanel.displayName = 'SecurityPrivacyPanel';

export default SecurityPrivacyPanel;
