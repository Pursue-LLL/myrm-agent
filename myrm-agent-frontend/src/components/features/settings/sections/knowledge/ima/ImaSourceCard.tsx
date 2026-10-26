'use client';

/**
 * [INPUT]
 * ./useImaSync::useImaSync (POS: status, polling and every user action)
 * ./imaCopy::deriveImaView, deriveImaSyncMode, IMA_DEDUP_REVIEW_ERROR_KEY (POS: which screen, what the sync is doing, which failure opens Duplicate Review)
 * ../WikiAgentScopeContext::useWikiAgentScope (POS: agent vault the card works on)
 * ./ImaConnectForm / ./ImaLibraryPicker / ./ImaSyncPanel / ./ImaReportDialog (POS: the card's screens)
 *
 * [OUTPUT]
 * ImaSourceCard (default): Tencent ima import card for Settings → Wiki
 *
 * [POS]
 * One card, one state machine: connect → choose libraries → importing / paused / up to date. Every screen is derived
 * from the server status, so a reload, a second window or a background run can never leave the card showing a step the
 * sync is no longer in. Failures surface as plain-language lines; server text and error codes never reach the screen.
 * A compile refused because duplicates await review also opens Duplicate Review (through the parent), where it unblocks.
 */

import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Skeleton } from '@/components/primitives/skeleton';
import type { ImaCredentialsInput, ImaSelectionInput, ImaStatus } from '@/services/wiki/ima';
import { useWikiAgentScope } from '../WikiAgentScopeContext';
import ImaConnectForm from './ImaConnectForm';
import ImaLibraryPicker from './ImaLibraryPicker';
import ImaReportDialog from './ImaReportDialog';
import ImaSyncPanel from './ImaSyncPanel';
import { deriveImaSyncMode, deriveImaView, IMA_DEDUP_REVIEW_ERROR_KEY, type ImaView } from './imaCopy';
import { useImaSync, type ImaResult } from './useImaSync';

interface ImaSourceCardProps {
  /** Opens Wiki → Duplicate Review, where compiling is unblocked. */
  onGoToDuplicateReview: () => void;
}

export default function ImaSourceCard({ onGoToDuplicateReview }: ImaSourceCardProps) {
  const t = useTranslations('settings.wiki.ima');
  const locale = useLocale();
  const { agentScopeId } = useWikiAgentScope();
  const ima = useImaSync(agentScopeId);
  const { status, busy } = ima;
  const [editingSelection, setEditingSelection] = useState(false);
  const [formErrorKey, setFormErrorKey] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);

  const view: ImaView | null = status ? deriveImaView(status, editingSelection) : null;

  const toastError = (errorKey: string) => toast.error(t(errorKey));

  const handleConnect = async (input: ImaCredentialsInput) => {
    setFormErrorKey(null);
    const result = await ima.connect(input);
    if (!result.ok) {
      setFormErrorKey(result.errorKey);
      return;
    }
    toast.success(t('connect.success'));
  };

  const handleStart = async (selection: ImaSelectionInput) => {
    setFormErrorKey(null);
    const result = await ima.startSync(selection, locale);
    if (!result.ok) {
      setFormErrorKey(result.errorKey);
      return;
    }
    setEditingSelection(false);
    toast.success(t('libraries.started'));
  };

  const handleSyncNow = async () => {
    const result = await ima.syncNow(locale);
    if (!result.ok) {
      toastError(result.errorKey);
      return;
    }
    toast.message(t('actions.syncNowStarted'));
  };

  const handleToggle = async (action: () => Promise<ImaResult>) => {
    const result = await action();
    if (!result.ok) {
      toastError(result.errorKey);
    }
  };

  const handleCompile = async () => {
    const result = await ima.compile();
    if (!result.ok) {
      toastError(result.errorKey);
      if (result.errorKey === IMA_DEDUP_REVIEW_ERROR_KEY) {
        onGoToDuplicateReview();
      }
      return;
    }
    if (result.value > 0) {
      toast.success(t('compile.queued', { count: result.value }));
    } else {
      toast.message(t('compile.nothing'));
    }
  };

  const handleRetry = async () => {
    const result = await ima.retryFailed();
    if (!result.ok) {
      toastError(result.errorKey);
      return;
    }
    setReportOpen(false);
    toast.success(t('report.retried', { count: result.value }));
  };

  const handleDisconnect = async () => {
    setDisconnectOpen(false);
    const result = await ima.disconnect();
    if (!result.ok) {
      toastError(result.errorKey);
      return;
    }
    setEditingSelection(false);
    toast.success(t('manage.disconnected'));
  };

  const badgeKey = status && view ? badgeKeyFor(status, view) : null;

  return (
    <Card className="border-border/60 bg-card/50">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-1.5">
            <CardTitle className="text-base">{t('title')}</CardTitle>
            <CardDescription>{t('description')}</CardDescription>
            {status?.connected && status.account_hint ? (
              <p className="text-xs text-muted-foreground">{t('account', { hint: status.account_hint })}</p>
            ) : null}
          </div>
          {badgeKey ? (
            <Badge variant="outline" className="shrink-0 font-normal">
              {t(badgeKey)}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {status === null && !ima.loadFailed ? (
          <div className="space-y-2" aria-busy="true" aria-label={t('loading')}>
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : null}

        {status === null && ima.loadFailed ? (
          <div className="space-y-2">
            <p role="alert" className="text-sm text-destructive">
              {t('loadError')}
            </p>
            <Button type="button" size="sm" variant="outline" onClick={() => void ima.refresh()}>
              {t('libraries.reload')}
            </Button>
          </div>
        ) : null}

        {status && (view === 'connect' || view === 'reconnect') ? (
          <ImaConnectForm
            reconnect={view === 'reconnect'}
            busy={busy === 'connect'}
            errorKey={formErrorKey}
            onSubmit={handleConnect}
          />
        ) : null}

        {status && view === 'choose' ? (
          <ImaLibraryPicker
            initialSelected={status.knowledge_bases}
            initialIncludeNotes={status.include_notes}
            busy={busy === 'start'}
            errorKey={formErrorKey}
            onCancel={
              editingSelection
                ? () => {
                    setFormErrorKey(null);
                    setEditingSelection(false);
                  }
                : undefined
            }
            onSubmit={handleStart}
          />
        ) : null}

        {status && view === 'sync' ? (
          <ImaSyncPanel
            status={status}
            busy={busy}
            onSyncNow={() => void handleSyncNow()}
            onPause={() => void handleToggle(ima.pause)}
            onResume={() => void handleToggle(ima.resume)}
            onCompile={() => void handleCompile()}
            onOpenReport={() => setReportOpen(true)}
          />
        ) : null}

        {status?.connected ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/50 pt-3">
            {view === 'sync' ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="-ml-2"
                onClick={() => setEditingSelection(true)}
              >
                {t('manage.changeSelection')}
              </Button>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="text-muted-foreground"
              disabled={busy === 'disconnect'}
              onClick={() => setDisconnectOpen(true)}
            >
              {t('manage.disconnect')}
            </Button>
          </div>
        ) : null}
      </CardContent>

      {reportOpen && status ? (
        <ImaReportDialog
          onOpenChange={setReportOpen}
          agentId={agentScopeId}
          counts={status.counts}
          retrying={busy === 'retry'}
          onRetryFailed={() => void handleRetry()}
        />
      ) : null}

      <AlertDialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('manage.disconnectTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('manage.disconnectBody')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleDisconnect()}>
              {t('manage.disconnectConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function badgeKeyFor(status: ImaStatus, view: ImaView): string | null {
  if (view === 'reconnect') {
    return 'badge.needsReconnect';
  }
  if (view !== 'sync') {
    return null;
  }
  switch (deriveImaSyncMode(status)) {
    case 'paused':
      return 'badge.paused';
    case 'upToDate':
      return 'badge.upToDate';
    default:
      return 'badge.syncing';
  }
}
