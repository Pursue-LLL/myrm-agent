'use client';

import { memo } from 'react';
import { useLocale, useTranslations } from 'next-intl';

import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { IconBot, IconLoader, IconPlug } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { cn } from '@/lib/utils/classnameUtils';

import { MOBILE_FULLSCREEN_DIALOG } from './dialogLayout';
import { PluginAgentsSection } from './PluginImportAgentsSection';
import { PluginImportDropzone } from './PluginImportDropzone';
import { PluginImportPreviewHeader } from './PluginImportPreviewHeader';
import { PluginImportResult } from './PluginImportResult';
import { PluginServersSection, PluginSkillsSection } from './PluginImportSections';
import { PluginTrustedSourceDisclosure } from './PluginTrustedSourceDisclosure';
import { usePluginImportFlow } from './usePluginImportFlow';

interface PluginImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImportComplete: () => void;
}

const PluginImportDialog = memo(({ open, onOpenChange, onImportComplete }: PluginImportDialogProps) => {
  const t = useTranslations('settings.plugins.import');
  const locale = useLocale();
  const flow = usePluginImportFlow({ onOpenChange, onImportComplete });
  const { preview, decisions, result, selected, isImporting } = flow;

  const nothingSelected = selected.skills + selected.servers + selected.agents === 0;
  const hasComponents =
    preview !== null && (preview.skills.length > 0 || preview.servers.length > 0 || preview.agents.length > 0);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          flow.reset();
        }
        onOpenChange(next);
      }}
    >
      <DialogContent
        className={cn('flex max-h-[85vh] max-w-3xl flex-col overflow-hidden p-0', MOBILE_FULLSCREEN_DIALOG)}
      >
        <DialogHeader className="border-b p-6 pb-4">
          <DialogTitle className="flex items-center gap-2 text-xl">
            <IconPlug className="h-5 w-5" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('subtitle')}</DialogDescription>
        </DialogHeader>

        <ScrollArea className="min-h-0 flex-1 bg-muted/10 px-4 sm:px-6">
          <div className="space-y-6 py-6">
            {result ? (
              <PluginImportResult result={result} />
            ) : !preview ? (
              <PluginImportDropzone
                isParsing={flow.isParsing}
                disabled={flow.isParsing || isImporting}
                error={flow.parseError}
                onFilesSelected={flow.handleFilesSelected}
              />
            ) : (
              <div className="space-y-6">
                <PluginImportPreviewHeader preview={preview} disabled={isImporting} onReselect={flow.reset} />

                {!hasComponents && (
                  <div className="rounded-xl border border-dashed p-6 text-center">
                    <p className="text-sm font-medium">{t('empty.title')}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{t('empty.hint')}</p>
                  </div>
                )}

                <PluginAgentsSection
                  items={preview.agents}
                  decisions={decisions.agents}
                  workspaceFileCount={preview.workspace_file_count}
                  disabled={isImporting}
                  onResolve={(id, resolution) => flow.setResolution('agents', id, resolution)}
                  onAll={(target) => flow.setAll('agents', target)}
                />

                {preview.skills.length > 0 && (
                  <PluginSkillsSection
                    items={preview.skills}
                    decisions={decisions.skills}
                    disabled={isImporting}
                    onResolve={(id, resolution) => flow.setResolution('skills', id, resolution)}
                    onAll={(target) => flow.setAll('skills', target)}
                  />
                )}

                {preview.servers.length > 0 && (
                  <PluginServersSection
                    items={preview.servers}
                    decisions={decisions.servers}
                    diagnostics={preview.diagnostics}
                    disabled={isImporting}
                    onResolve={(id, resolution) => flow.setResolution('servers', id, resolution)}
                    onAll={(target) => flow.setAll('servers', target)}
                  />
                )}

                {(preview.skills.length > 0 || preview.servers.length > 0) && (
                  <div className="space-y-2">
                    <label className="flex items-center gap-2 text-sm font-medium">
                      <IconBot className="h-4 w-4 text-muted-foreground" />
                      {t('bind.label')}
                    </label>
                    <Select
                      value={flow.bindAgentId ?? undefined}
                      onValueChange={flow.setBindAgentId}
                      disabled={isImporting}
                    >
                      <SelectTrigger className="w-full sm:w-[280px]">
                        <SelectValue placeholder={t('bind.placeholder')} />
                      </SelectTrigger>
                      <SelectContent>
                        {flow.agents.map((agent) => (
                          <SelectItem key={agent.id} value={agent.id}>
                            {getBuiltinAgentName(agent.id, agent.name || agent.id, locale)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">{t('bind.hint')}</p>
                  </div>
                )}

                <PluginTrustedSourceDisclosure
                  trusted={flow.trusted}
                  onTrustChange={flow.setTrusted}
                  disabled={isImporting}
                />
              </div>
            )}
          </div>
        </ScrollArea>

        {result ? (
          <div className="flex items-center justify-end gap-2 border-t p-4">
            <Button variant="outline" size="sm" onClick={flow.reset}>
              {t('actions.importAnother')}
            </Button>
            <Button size="sm" onClick={flow.close}>
              {t('actions.done')}
            </Button>
          </div>
        ) : (
          preview && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t p-4">
              <div className="text-xs text-muted-foreground">
                {t('summary', { agents: selected.agents, skills: selected.skills, servers: selected.servers })}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={flow.reset} disabled={isImporting}>
                  {t('actions.cancel')}
                </Button>
                <Button
                  size="sm"
                  onClick={() => void flow.confirm()}
                  disabled={isImporting || nothingSelected || !flow.trusted}
                >
                  {isImporting && <IconLoader className="mr-2 h-4 w-4 animate-spin" />}
                  {t('actions.confirm')}
                </Button>
              </div>
            </div>
          )
        )}
      </DialogContent>
    </Dialog>
  );
});

PluginImportDialog.displayName = 'PluginImportDialog';

export default PluginImportDialog;
