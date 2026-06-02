'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { IconExternalLink } from './catalog-icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from '@/hooks/useToast';
import useConfigStore from '@/store/useConfigStore';
import type { MCPServiceConfig } from '@/store/config/types';
import type { CatalogEntry } from './catalog-types';

interface IntegrationConnectDialogProps {
  entry: CatalogEntry;
  locale: string;
  onClose: () => void;
  onConnected: () => void;
}

export const IntegrationConnectDialog = memo<IntegrationConnectDialogProps>(
  ({ entry, locale, onClose, onConnected }) => {
    const t = useTranslations('settings.integrationCatalog.connectDialog');
    const hasMultiFields = entry.credentialFields && entry.credentialFields.length > 0;

    const [credential, setCredential] = useState('');
    const [fieldValues, setFieldValues] = useState<Record<string, string>>(() =>
      hasMultiFields ? Object.fromEntries(entry.credentialFields!.map((f) => [f.key, ''])) : {},
    );
    const [connecting, setConnecting] = useState(false);
    const { mcpConfigs, setMCPConfigs } = useConfigStore();

    const helpText = locale === 'zh' && entry.helpTextZh ? entry.helpTextZh : entry.helpText;

    const handleFieldChange = useCallback((key: string, value: string) => {
      setFieldValues((prev) => ({ ...prev, [key]: value }));
    }, []);

    const handleConnect = useCallback(() => {
      if (entry.authType !== 'none') {
        if (hasMultiFields) {
          const empty = entry.credentialFields!.find((f) => !fieldValues[f.key]?.trim());
          if (empty) {
            const label = locale === 'zh' && empty.labelZh ? empty.labelZh : empty.label;
            toast({ title: `${label} ${t('credentialRequired')}`, variant: 'destructive' });
            return;
          }
        } else if (!credential.trim()) {
          toast({ title: t('credentialRequired'), variant: 'destructive' });
          return;
        }
      }

      setConnecting(true);
      try {
        if (entry.connectorType === 'mcp' && entry.mcpConfig) {
          const mcpCfg = entry.mcpConfig as {
            name: string;
            type: string;
            url?: string;
            command?: string;
            args?: string[];
            env?: Record<string, string>;
            description?: string;
          };

          let finalArgs = mcpCfg.args || [];
          const envMap: Record<string, string> = { ...mcpCfg.env };

          if (hasMultiFields) {
            for (const field of entry.credentialFields!) {
              const val = fieldValues[field.key]?.trim() || '';
              if (field.inject === 'arg_placeholder') {
                finalArgs = finalArgs.map((a) => (a === field.key ? val : a));
              } else {
                envMap[field.key] = val;
              }
            }
          } else if (entry.envKey && credential.trim()) {
            envMap[entry.envKey] = credential.trim();
          }

          const newConfig: MCPServiceConfig = {
            name: mcpCfg.name,
            type: mcpCfg.type as 'sse' | 'stdio' | 'streamable_http',
            url: mcpCfg.url || '',
            command: mcpCfg.command || '',
            args: finalArgs,
            description: mcpCfg.description || '',
            enabled: true,
            extra_params: Object.keys(envMap).length > 0 ? { env: envMap } : null,
          };

          const exists = mcpConfigs.some((c) => c.name === newConfig.name);
          if (exists) {
            toast({ title: t('alreadyConnected'), variant: 'destructive' });
            setConnecting(false);
            return;
          }

          setMCPConfigs([...mcpConfigs, newConfig]);
          toast({ title: t('connectSuccess', { name: entry.name }) });
          onConnected();
        }
      } catch (e) {
        toast({
          title: t('connectFailed'),
          description: String(e),
          variant: 'destructive',
        });
      } finally {
        setConnecting(false);
      }
    }, [entry, credential, fieldValues, hasMultiFields, locale, mcpConfigs, setMCPConfigs, onConnected, t]);

    return (
      <Dialog open onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('title', { name: entry.name })}</DialogTitle>
            <DialogDescription>
              {locale === 'zh' && entry.descriptionZh ? entry.descriptionZh : entry.description}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {entry.authType !== 'none' && (
              <>
                {hasMultiFields ? (
                  <div className="space-y-3">
                    {entry.credentialFields!.map((field) => (
                      <div key={field.key} className="space-y-1.5">
                        <Label className="text-sm">
                          {locale === 'zh' && field.labelZh ? field.labelZh : field.label}
                        </Label>
                        <Input
                          type="password"
                          value={fieldValues[field.key] || ''}
                          onChange={(e) => handleFieldChange(field.key, e.target.value)}
                          placeholder={locale === 'zh' && field.labelZh ? field.labelZh : field.label}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label>{t('credentialLabel')}</Label>
                    <Input
                      type="password"
                      value={credential}
                      onChange={(e) => setCredential(e.target.value)}
                      placeholder={t('credentialPlaceholder')}
                    />
                  </div>
                )}

                {helpText && <p className="text-muted-foreground text-xs">{helpText}</p>}

                {entry.helpUrl && (
                  <a
                    href={entry.helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary inline-flex items-center gap-1 text-xs hover:underline"
                  >
                    {t('getCredential')}
                    <IconExternalLink className="h-3 w-3" />
                  </a>
                )}
              </>
            )}

            {entry.authType === 'none' && <p className="text-muted-foreground text-sm">{t('noAuthRequired')}</p>}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t('cancel')}
            </Button>
            <Button onClick={handleConnect} disabled={connecting}>
              {connecting ? t('connecting') : t('connect')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  },
);

IntegrationConnectDialog.displayName = 'IntegrationConnectDialog';
