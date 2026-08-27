'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: i18n support)
 * - @/services/system::systemService (POS: Debug bundle export URL generator)
 * - @/components/features/icons/PremiumIcons (POS: Standard premium UI icons)
 *
 * [OUTPUT]
 * - SupportDebugBundleCard: Settings card for one-click redacted support zip bundle export.
 *
 * [POS]
 * Settings -> Developer Center -> Import/Export technical support bundle exporter.
 */

import React, { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import { Label } from '@/components/primitives/label';
import {
  IconDownload,
  IconLoader,
  IconShieldAlert,
  IconWrench,
} from '@/components/features/icons/PremiumIcons';
import { toast } from '@/hooks/shared/useToast';
import { systemService } from '@/services/system';

export const SupportDebugBundleCard = memo(() => {
  const t = useTranslations('settings.supportDebugBundle');
  const [includeTraces, setIncludeTraces] = useState(true);
  const [includeProfiles, setIncludeProfiles] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const handleDownload = useCallback(async () => {
    setDownloading(true);
    try {
      const exportUrl = systemService.getSupportDebugBundleUrl({
        includeTraces,
        includeProfiles,
      });

      const response = await fetch(exportUrl, { method: 'GET' });
      if (!response.ok) {
        throw new Error(`Export failed with HTTP status ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `myrm-support-debug-${new Date().toISOString().replace(/[:.]/g, '-')}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: t('exportSuccessTitle'),
        description: t('exportSuccessDesc'),
      });
    } catch (error) {
      toast({
        title: t('exportFailedTitle'),
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      });
    } finally {
      setDownloading(false);
    }
  }, [includeTraces, includeProfiles, t]);

  return (
    <SettingsSection title={t('title')}>
      <div className="space-y-4" data-testid="support-debug-bundle-card">
        <p className="text-sm text-muted-foreground">{t('description')}</p>

        {/* 隐私与脱敏保证提示 */}
        <div className="flex items-start gap-2.5 p-3 rounded-lg border border-primary/20 bg-primary/5 text-xs text-muted-foreground">
          <IconShieldAlert className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-medium text-foreground">{t('privacyNoticeTitle')}</span>
            <p className="leading-relaxed">{t('privacyNoticeDesc')}</p>
          </div>
        </div>

        {/* 导出配置项 */}
        <div className="space-y-3 pt-1">
          <div className="flex items-center justify-between gap-4 p-3 border border-border/60 rounded-lg bg-background/50">
            <div className="space-y-0.5">
              <Label htmlFor="include-traces" className="text-sm font-medium cursor-pointer">
                {t('includeTraces')}
              </Label>
              <p className="text-xs text-muted-foreground">{t('includeTracesDesc')}</p>
            </div>
            <Switch
              id="include-traces"
              checked={includeTraces}
              onCheckedChange={setIncludeTraces}
              data-testid="toggle-include-traces"
            />
          </div>

          <div className="flex items-center justify-between gap-4 p-3 border border-border/60 rounded-lg bg-background/50">
            <div className="space-y-0.5">
              <Label htmlFor="include-profiles" className="text-sm font-medium cursor-pointer">
                {t('includeProfiles')}
              </Label>
              <p className="text-xs text-muted-foreground">{t('includeProfilesDesc')}</p>
            </div>
            <Switch
              id="include-profiles"
              checked={includeProfiles}
              onCheckedChange={setIncludeProfiles}
              data-testid="toggle-include-profiles"
            />
          </div>
        </div>

        {/* 导出按钮 */}
        <div className="pt-2 flex justify-end">
          <Button
            type="button"
            variant="default"
            size="sm"
            onClick={handleDownload}
            disabled={downloading}
            data-testid="export-debug-bundle-btn"
            className="gap-2"
          >
            {downloading ? (
              <>
                <IconLoader className="w-4 h-4 animate-spin" />
                <span>{t('exporting')}</span>
              </>
            ) : (
              <>
                <IconDownload className="w-4 h-4" />
                <span>{t('exportButton')}</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </SettingsSection>
  );
});

SupportDebugBundleCard.displayName = 'SupportDebugBundleCard';
export default SupportDebugBundleCard;
