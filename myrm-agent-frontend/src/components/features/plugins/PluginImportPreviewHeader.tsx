'use client';

import { memo, useEffect } from 'react';
import { useTranslations } from 'next-intl';

import { IconAlertTriangle, IconBot, IconPlug, IconShieldCheck } from '@/components/features/icons/PremiumIcons';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';

import { diagnosticMessageKey, diagnosticScope, headerDiagnostics } from './pluginDiagnostics';
import { getCapabilityTierBadgeStyle } from './PluginImportSections';
import type { PluginMeta, PluginPreviewPayload } from './pluginImportTypes';

const RISK_STYLES: Record<string, string> = {
  high: 'border-amber-500/50 text-amber-600 dark:text-amber-400 bg-amber-500/10',
  medium: 'border-blue-500/50 text-blue-600 dark:text-blue-400 bg-blue-500/10',
  low: 'border-emerald-500/50 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10',
};

function PluginCard({
  plugin,
  disabled,
  onReselect,
}: {
  plugin: PluginMeta;
  disabled: boolean;
  onReselect: () => void;
}) {
  const t = useTranslations('settings.plugins.import');
  return (
    <div className="flex flex-col justify-between gap-3 rounded-xl border bg-background p-4 sm:flex-row sm:items-start">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <IconPlug className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-medium">{plugin.name}</h3>
            {plugin.version && (
              <Badge variant="outline" className="text-xs">
                v{plugin.version}
              </Badge>
            )}
            {plugin.license && (
              <Badge variant="secondary" className="text-xs">
                {plugin.license}
              </Badge>
            )}
            {plugin.risk_level && (
              <Badge
                variant={plugin.risk_level === 'critical' ? 'destructive' : 'outline'}
                className={cn('text-xs font-normal', RISK_STYLES[plugin.risk_level])}
              >
                <IconShieldCheck className="mr-1 inline-block h-3 w-3" />
                {t(`capabilities.risk.${plugin.risk_level}` as Parameters<typeof t>[0])}
              </Badge>
            )}
          </div>
          {plugin.description && (
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{plugin.description}</p>
          )}
          {plugin.capabilities.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="mr-0.5 text-[11px] font-medium text-muted-foreground">{t('capabilities.title')}:</span>
              {plugin.capabilities.map((cap) => (
                <Badge
                  key={cap}
                  variant="outline"
                  className={cn('px-1.5 py-0 text-[10px] font-normal', getCapabilityTierBadgeStyle(cap))}
                >
                  {t(`capabilities.${cap}` as Parameters<typeof t>[0])}
                </Badge>
              ))}
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            {plugin.author?.name && (
              <span className="flex items-center gap-1">
                <IconBot className="h-3 w-3" />
                {plugin.author.name}
              </span>
            )}
            {plugin.keywords.slice(0, 5).map((keyword) => (
              <Badge key={keyword} variant="outline" className="px-1.5 py-0 text-[10px]">
                {keyword}
              </Badge>
            ))}
          </div>
        </div>
      </div>
      <Button variant="ghost" size="sm" onClick={onReselect} disabled={disabled}>
        {t('actions.reselect')}
      </Button>
    </div>
  );
}

interface PluginImportPreviewHeaderProps {
  preview: PluginPreviewPayload;
  disabled: boolean;
  onReselect: () => void;
}

/** Plugin identity and everything the user should read before choosing components. */
export const PluginImportPreviewHeader = memo(({ preview, disabled, onReselect }: PluginImportPreviewHeaderProps) => {
  const t = useTranslations('settings.plugins.import');
  const { plugin, deployment } = preview;
  const diagnostics = headerDiagnostics(preview.diagnostics);

  // The backend's English wording is for developers; users read the localized sentence below.
  useEffect(() => {
    for (const diagnostic of preview.diagnostics) {
      console.warn(`Plugin diagnostic [${diagnostic.component}] ${diagnostic.code}: ${diagnostic.message}`);
    }
  }, [preview.diagnostics]);

  return (
    <>
      <PluginCard plugin={plugin} disabled={disabled} onReselect={onReselect} />

      {plugin.capability_diff?.has_escalation && (
        <Alert variant="destructive" className="py-2.5">
          <IconAlertTriangle className="h-4 w-4" />
          <AlertTitle className="text-xs font-semibold">{t('capabilities.escalationTitle')}</AlertTitle>
          <AlertDescription className="mt-0.5 text-xs">
            {t('capabilities.escalationWarning', {
              added: plugin.capability_diff.added
                .map((capability) => t(`capabilities.${capability}` as Parameters<typeof t>[0]))
                .join(', '),
            })}
          </AlertDescription>
        </Alert>
      )}

      {(!deployment.allows_local_skills || !deployment.allow_stdio) && (
        <Alert className="py-2.5">
          <IconAlertTriangle className="h-4 w-4" />
          <AlertDescription className="space-y-0.5 text-xs">
            {!deployment.allows_local_skills && <p>{t('deployment.noLocalSkills')}</p>}
            {!deployment.allow_stdio && <p>{t('deployment.noLocalConnectors')}</p>}
          </AlertDescription>
        </Alert>
      )}

      {diagnostics.length > 0 && (
        <div className="space-y-2">
          {diagnostics.map((diagnostic, index) => {
            const { scope, name } = diagnosticScope(diagnostic.component);
            return (
              <Alert key={index} variant={diagnostic.level === 'error' ? 'destructive' : 'default'} className="py-2">
                <IconAlertTriangle className="h-4 w-4" />
                <AlertTitle className="text-xs font-medium">
                  {t(`diagnostics.scope.${scope}` as Parameters<typeof t>[0], { name })}
                </AlertTitle>
                <AlertDescription className="text-xs">
                  {t(`diagnostics.messages.${diagnosticMessageKey(diagnostic.code)}` as Parameters<typeof t>[0])}
                </AlertDescription>
              </Alert>
            );
          })}
        </div>
      )}
    </>
  );
});
PluginImportPreviewHeader.displayName = 'PluginImportPreviewHeader';
