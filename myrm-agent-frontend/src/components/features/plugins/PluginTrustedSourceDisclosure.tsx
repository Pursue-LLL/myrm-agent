'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { isSandbox } from '@/lib/deploy-mode';
import { IconAlertTriangle, IconShieldCheck, IconTerminal, IconFolder } from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';

export interface PluginTrustedSourceDisclosureProps {
  trusted: boolean;
  onTrustChange: (trusted: boolean) => void;
  disabled?: boolean;
}

export const PluginTrustedSourceDisclosure = memo(function PluginTrustedSourceDisclosure({
  trusted,
  onTrustChange,
  disabled = false,
}: PluginTrustedSourceDisclosureProps) {
  const t = useTranslations('settings.plugins.import.security');
  const sandbox = isSandbox();

  return (
    <div
      data-testid="plugin-trusted-source-disclosure"
      className={cn(
        'rounded-lg border p-3.5 space-y-3 transition-colors',
        'border-amber-500/30 bg-amber-500/5 dark:bg-amber-950/20 text-amber-900 dark:text-amber-200',
      )}
    >
      <div className="flex items-start gap-2.5">
        <IconAlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
        <div className="space-y-1.5 flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-xs font-semibold leading-none tracking-tight text-amber-900 dark:text-amber-200">
              {t('trustDisclosureTitle')}
            </h4>
            <Badge
              variant="outline"
              className={cn(
                'text-[10px] h-4 px-1.5 font-normal border-amber-500/40',
                sandbox
                  ? 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30'
                  : 'bg-amber-500/15 text-amber-800 dark:text-amber-300',
              )}
            >
              {sandbox ? (
                <span className="flex items-center gap-1">
                  <IconFolder className="w-2.5 h-2.5" />
                  Cloud Sandbox
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <IconTerminal className="w-2.5 h-2.5" />
                  Local OS Permissions
                </span>
              )}
            </Badge>
          </div>

          <p className="text-[11px] leading-relaxed text-amber-800/90 dark:text-amber-300/80">
            {sandbox ? t('trustDisclosureCloud') : t('trustDisclosureLocal')}
          </p>

          <p className="text-[11px] leading-relaxed text-amber-700/80 dark:text-amber-400/70 border-t border-amber-500/20 pt-1.5">
            {t('trustRiskHint')}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2.5 pt-0.5">
        <input
          id="trusted-source-checkbox"
          data-testid="trusted-source-checkbox"
          type="checkbox"
          checked={trusted}
          disabled={disabled}
          onChange={(e) => onTrustChange(e.target.checked)}
          className="h-4 w-4 rounded border-amber-500/50 text-amber-600 focus:ring-amber-500 focus:ring-offset-0 bg-background cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <label
          htmlFor="trusted-source-checkbox"
          className="text-xs font-medium text-amber-950 dark:text-amber-100 cursor-pointer select-none leading-snug"
        >
          {t('trustedCheckboxLabel')}
        </label>
      </div>
    </div>
  );
});

PluginTrustedSourceDisclosure.displayName = 'PluginTrustedSourceDisclosure';

export default PluginTrustedSourceDisclosure;
