'use client';

/**
 * [INPUT]
 * - @/services/workspaceTrust::previewWorkspaceTrustManifest, decideWorkspaceTrust
 *
 * [OUTPUT]
 * - WorkspaceTrustFolderGate: pre-bind disclosure dialog (FolderGate)
 *
 * [POS]
 * Shown before linking a project workspace folder. User must choose Trust or Restrict
 * so side-channel execution (skills, rules, local MCP) follows an explicit decision.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FolderOpen, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import {
  decideWorkspaceTrust,
  previewWorkspaceTrustManifest,
  type WorkspaceTrustManifest,
} from '@/services/workspaceTrust';
import { shortenHomePath } from '@/lib/directoryBrowseRecent';

export interface WorkspaceTrustFolderGateProps {
  open: boolean;
  folderPath: string | null;
  onOpenChange: (open: boolean) => void;
  onDecided: (path: string, level: 'TRUSTED' | 'RESTRICTED') => void | Promise<void>;
}

const WorkspaceTrustFolderGate = memo(
  ({ open, folderPath, onOpenChange, onDecided }: WorkspaceTrustFolderGateProps) => {
    const t = useTranslations('project.workspaceMount.folderGate');
    const [manifest, setManifest] = useState<WorkspaceTrustManifest | null>(null);
    const [loading, setLoading] = useState(false);
    const [deciding, setDeciding] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadManifest = useCallback(async () => {
      if (!folderPath) {
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const preview = await previewWorkspaceTrustManifest(folderPath);
        setManifest(preview);
      } catch {
        setError(t('loadFailed'));
        setManifest(null);
      } finally {
        setLoading(false);
      }
    }, [folderPath, t]);

    const handleOpenChange = useCallback(
      (nextOpen: boolean) => {
        if (!nextOpen) {
          setManifest(null);
          setError(null);
        }
        onOpenChange(nextOpen);
      },
      [onOpenChange],
    );

    useEffect(() => {
      if (open && folderPath) {
        void loadManifest();
      }
    }, [open, folderPath, loadManifest]);

    const handleDecide = useCallback(
      async (level: 'TRUSTED' | 'RESTRICTED') => {
        if (!folderPath) {
          return;
        }
        setDeciding(true);
        try {
          await decideWorkspaceTrust(folderPath, level);
          await onDecided(folderPath, level);
          onOpenChange(false);
          setManifest(null);
        } catch {
          setError(t('decideFailed'));
        } finally {
          setDeciding(false);
        }
      },
      [folderPath, onDecided, onOpenChange, t],
    );

    return (
      <AlertDialog open={open} onOpenChange={handleOpenChange}>
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <FolderOpen className="h-5 w-5 text-primary" />
              {t('title')}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3 text-left text-sm text-muted-foreground">
                <p>{t('description')}</p>
                {folderPath && (
                  <p className="rounded-md bg-muted/50 px-2 py-1 font-mono text-xs text-foreground">
                    {shortenHomePath(folderPath)}
                  </p>
                )}
                {loading && <p className="text-xs">{t('loading')}</p>}
                {error && <p className="text-xs text-destructive">{error}</p>}
                {manifest && !loading && (
                  <div className="space-y-2 rounded-lg border border-border/60 bg-muted/20 p-3">
                    <p className="text-xs font-medium text-foreground">{t('disclosureTitle')}</p>
                    <ul className="space-y-1.5 text-xs">
                      <li className="flex items-center justify-between gap-2">
                        <span>{t('skills')}</span>
                        <Badge variant="secondary">{manifest.skill_count}</Badge>
                      </li>
                      <li className="flex items-center justify-between gap-2">
                        <span>{t('rules')}</span>
                        <Badge variant="secondary">{manifest.rule_count}</Badge>
                      </li>
                      {manifest.has_myrm_config && (
                        <li className="text-amber-700 dark:text-amber-300">{t('hasMyrmConfig')}</li>
                      )}
                      {manifest.repo_command_prefixes.length > 0 && (
                        <li>
                          <span className="block mb-1">{t('repoCommands')}</span>
                          <div className="flex flex-wrap gap-1">
                            {manifest.repo_command_prefixes.map((prefix) => (
                              <Badge key={prefix} variant="outline" className="font-mono text-[10px]">
                                {prefix}
                              </Badge>
                            ))}
                          </div>
                        </li>
                      )}
                    </ul>
                    <p className="text-[11px] leading-relaxed">{t('restrictedHint')}</p>
                  </div>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex-col gap-2 sm:flex-row">
            <AlertDialogCancel disabled={deciding}>{t('cancel')}</AlertDialogCancel>
            <Button
              variant="outline"
              disabled={loading || deciding || !manifest}
              onClick={() => void handleDecide('RESTRICTED')}
            >
              <ShieldAlert className="mr-1.5 h-4 w-4" />
              {t('restrict')}
            </Button>
            <Button disabled={loading || deciding || !manifest} onClick={() => void handleDecide('TRUSTED')}>
              <ShieldCheck className="mr-1.5 h-4 w-4" />
              {t('trust')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  },
);

WorkspaceTrustFolderGate.displayName = 'WorkspaceTrustFolderGate';

export default WorkspaceTrustFolderGate;
