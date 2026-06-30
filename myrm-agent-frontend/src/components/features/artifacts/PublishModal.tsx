'use client';

import Link from 'next/link';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Loader2, Globe, CheckCircle2, XCircle, Copy, ExternalLink } from 'lucide-react';
import { Artifact } from '@/store/chat/types';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  buildPublishStatusWsUrl,
  fetchArtifactPublications,
  fetchHostingTargets,
  fetchPublishPreflight,
  fetchTargetCredentialStatus,
  publishArtifact,
  PROVIDER_LABELS,
  type HostingTarget,
  type PublishPreflight,
  type ArtifactPublication,
} from '@/services/hosting';

export interface PublishedArtifactUpdate {
  publications: ArtifactPublication[];
  latest_version_id?: string | null;
}

interface PublishModalProps {
  artifact: Artifact;
  open: boolean;
  onClose: () => void;
  onPublished?: (update: PublishedArtifactUpdate) => void;
  initialTargetId?: string;
}

export const PublishModal: React.FC<PublishModalProps> = ({
  artifact,
  open,
  onClose,
  onPublished,
  initialTargetId,
}) => {
  const t = useTranslations('artifacts.publish');
  const [targets, setTargets] = useState<HostingTarget[]>([]);
  const [selectedTargetId, setSelectedTargetId] = useState('');
  const [tokenOverride, setTokenOverride] = useState('');
  const [status, setStatus] = useState<'IDLE' | 'PUBLISHING' | 'SUCCESS' | 'ERROR'>('IDLE');
  const [logs, setLogs] = useState<string[]>([]);
  const [publishUrl, setPublishUrl] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [platformAvailable, setPlatformAvailable] = useState(false);
  const [preflight, setPreflight] = useState<PublishPreflight | null>(null);
  const isIntentionalClose = useRef(false);

  const selectedTarget = targets.find((item) => item.id === selectedTargetId) ?? null;
  const showVercelToken = selectedTarget?.provider_type === 'vercel';

  const canPublish =
    Boolean(selectedTargetId) &&
    (platformAvailable || !showVercelToken || tokenOverride.trim().length > 0) &&
    preflight?.deployable !== false;

  const notifyPublished = useCallback(
    (payload: PublishedArtifactUpdate) => {
      onPublished?.(payload);
    },
    [onPublished],
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    setStatus('IDLE');
    setLogs([]);
    setPublishUrl('');
    setErrorMsg('');
    setCopied(false);
    setPlatformAvailable(false);
    setTokenOverride('');
    isIntentionalClose.current = false;

    let cancelled = false;

    const bootstrap = async () => {
      setLoading(true);
      try {
        const loadedTargets = await fetchHostingTargets();
        if (cancelled) {
          return;
        }
        setTargets(loadedTargets);
        const preferred =
          initialTargetId ??
          loadedTargets.find((item) => item.is_default)?.id ??
          loadedTargets[0]?.id ??
          '';
        setSelectedTargetId(preferred);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, [open, initialTargetId]);

  useEffect(() => {
    if (!open || !selectedTargetId) {
      return;
    }

    let cancelled = false;

    const loadPreflightAndCreds = async () => {
      setLoading(true);
      try {
        const [preflightResult, credStatus] = await Promise.all([
          fetchPublishPreflight(artifact.id, selectedTargetId),
          fetchTargetCredentialStatus(selectedTargetId),
        ]);
        if (cancelled) {
          return;
        }
        setPreflight(preflightResult);
        setPlatformAvailable(credStatus.platform_available || credStatus.configured);
        if (preflightResult && !preflightResult.deployable) {
          setErrorMsg(preflightResult.message);
        } else {
          setErrorMsg('');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadPreflightAndCreds();

    return () => {
      cancelled = true;
    };
  }, [open, artifact.id, selectedTargetId]);

  const handlePublish = async () => {
    if (!selectedTargetId) {
      setErrorMsg(t('errors.noTarget'));
      return;
    }
    if (preflight && !preflight.deployable) {
      toast.error(preflight.message, { description: preflight.hint ?? undefined });
      return;
    }
    if (!canPublish) {
      setErrorMsg(t('errors.tokenRequired'));
      return;
    }

    setStatus('PUBLISHING');
    setLogs([t('logs.initiating')]);
    setErrorMsg('');
    isIntentionalClose.current = false;

    try {
      const data = await publishArtifact(artifact.id, selectedTargetId, tokenOverride.trim());
      const providerRef = data.provider_publication_ref;
      const initialUrl = data.publication_url || data.url;
      const publicationStatus = data.publication_status || data.status || 'PUBLISHING';
      const latestVersionId = data.latest_version_id ?? data.publication_version_id ?? null;

      const syncPublications = async () => {
        const publications = await fetchArtifactPublications(artifact.id);
        notifyPublished({ publications, latest_version_id: latestVersionId });
      };

      if (initialUrl) {
        setPublishUrl(initialUrl);
      }
      await syncPublications();

      if (!providerRef) {
        if (publicationStatus === 'READY' && initialUrl) {
          setStatus('SUCCESS');
          return;
        }
        throw new Error(t('errors.noPublicationId'));
      }

      setLogs((prev) => [...prev, t('logs.created', { id: providerRef }), t('logs.connecting')]);

      const wsUrl = buildPublishStatusWsUrl(artifact.id, providerRef, selectedTargetId);
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth' }));
      };

      ws.onmessage = (event) => {
        const statusData = JSON.parse(event.data) as { status?: string; url?: string };
        const currentStatus = statusData.status ?? 'UNKNOWN';

        setLogs((prev) => [...prev, t('logs.status', { status: currentStatus })]);

        if (currentStatus === 'READY' || currentStatus === 'ready') {
          const url = statusData.url ?? initialUrl;
          setStatus('SUCCESS');
          setPublishUrl(url);
          void syncPublications();
          isIntentionalClose.current = true;
          ws.close();
        } else if (currentStatus === 'ERROR' || currentStatus === 'CANCELED') {
          setStatus('ERROR');
          setErrorMsg(t('errors.publicationStatus', { status: currentStatus.toLowerCase() }));
          isIntentionalClose.current = true;
          ws.close();
        }
      };

      ws.onclose = () => {
        setStatus((currentStatus) => {
          if (currentStatus === 'PUBLISHING' && !isIntentionalClose.current) {
            setErrorMsg(t('errors.networkLost'));
            return 'ERROR';
          }
          return currentStatus;
        });
      };

      ws.onerror = () => {
        setLogs((prev) => [...prev, t('logs.wsError')]);
      };
    } catch (error: unknown) {
      setStatus('ERROR');
      const errorMessage = error instanceof Error ? error.message : t('errors.unexpected');
      setErrorMsg(errorMessage);
      setLogs((prev) => [...prev, t('logs.error', { message: errorMessage })]);
    }
  };

  const handleCopy = async () => {
    if (!publishUrl) {
      return;
    }
    try {
      await writeToClipboard(publishUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy', err);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-md bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-2xl overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent pointer-events-none" />

        <DialogHeader className="relative z-10">
          <DialogTitle className="flex items-center gap-2 text-xl font-semibold">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <Globe className="w-5 h-5" />
            </div>
            {t('title')}
          </DialogTitle>
          <DialogDescription className="pt-2">{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4 relative z-10">
          {status === 'IDLE' && (
            <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
              {targets.length === 0 ? (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground bg-muted/40 border border-dashed rounded-lg px-3 py-3">
                    {t('noTargetsHint')}
                  </p>
                  <Button asChild variant="outline" className="w-full">
                    <Link href="/settings/hosting">{t('openHostingSettings')}</Link>
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="hosting-target">{t('targetLabel')}</Label>
                  <select
                    id="hosting-target"
                    value={selectedTargetId}
                    onChange={(e) => setSelectedTargetId(e.target.value)}
                    disabled={loading}
                    className="w-full h-10 rounded-md border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-950 px-3 text-sm"
                  >
                    {targets.map((target) => (
                      <option key={target.id} value={target.id}>
                        {target.name} ({PROVIDER_LABELS[target.provider_type]})
                        {target.is_default ? ` · ${t('defaultTarget')}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {platformAvailable && showVercelToken && (
                <p className="text-sm text-primary bg-primary/5 border border-primary/20 rounded-lg px-3 py-2">
                  {t('platformHostingHint')}
                </p>
              )}

              {showVercelToken && targets.length > 0 && (
                <div className="space-y-2">
                  <Label htmlFor="token" className="text-sm font-medium">
                    {platformAvailable ? t('tokenLabelOptional') : t('tokenLabel')}
                  </Label>
                  <Input
                    id="token"
                    type="password"
                    value={tokenOverride}
                    onChange={(e) => setTokenOverride(e.target.value)}
                    placeholder={t('tokenPlaceholder')}
                    disabled={loading}
                    className="w-full font-mono text-sm bg-gray-50 dark:bg-gray-950 border-gray-200 dark:border-gray-800 focus-visible:ring-primary"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400">{t('tokenHint')}</p>
                </div>
              )}

              {preflight && !preflight.deployable && preflight.hint && (
                <p className="text-sm text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 p-2 rounded-md border border-amber-200 dark:border-amber-900">
                  {preflight.hint}
                </p>
              )}
              {errorMsg && (
                <p className="text-sm text-red-500 bg-red-50 dark:bg-red-950/50 p-2 rounded-md border border-red-100 dark:border-red-900">
                  {errorMsg}
                </p>
              )}
              <Button
                onClick={() => void handlePublish()}
                className="w-full shadow-lg shadow-primary/20 transition-all hover:scale-[1.02]"
                disabled={!canPublish || loading || targets.length === 0}
              >
                {t('publishNow')}
              </Button>
            </div>
          )}

          {status === 'PUBLISHING' && (
            <div className="space-y-5 animate-in fade-in zoom-in-95 duration-300">
              <div className="flex flex-col items-center justify-center py-6 gap-4">
                <div className="relative">
                  <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
                  <Loader2 className="w-10 h-10 animate-spin text-primary relative z-10" />
                </div>
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300 animate-pulse">{t('publishing')}</p>
              </div>
              <div className="bg-gray-950 text-gray-300 p-4 rounded-lg h-40 overflow-y-auto font-mono text-xs shadow-inner border border-gray-800 scrollbar-thin scrollbar-thumb-gray-700">
                {logs.map((log, i) => (
                  <div key={i} className="mb-1 opacity-80 hover:opacity-100 transition-opacity">
                    <span className="text-gray-500 mr-2">[{new Date().toLocaleTimeString()}]</span>
                    {log}
                  </div>
                ))}
              </div>
            </div>
          )}

          {status === 'SUCCESS' && (
            <div className="space-y-6 text-center animate-in fade-in zoom-in-95 duration-500">
              <div className="flex justify-center">
                <div className="relative">
                  <div className="absolute inset-0 bg-green-500/20 rounded-full blur-xl animate-pulse" />
                  <CheckCircle2 className="w-16 h-16 text-green-500 relative z-10" />
                </div>
              </div>
              <div>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('successTitle')}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">{t('successDescription')}</p>
              </div>

              <div className="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm">
                <Input
                  value={publishUrl}
                  readOnly
                  className="bg-transparent border-none focus-visible:ring-0 font-mono text-sm text-primary"
                />
                <div className="flex gap-1 pr-1">
                  <Button size="icon" variant="ghost" onClick={() => void handleCopy()} className="hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg">
                    {copied ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4 text-gray-500" />}
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => window.open(publishUrl, '_blank')}
                    className="hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg"
                  >
                    <ExternalLink className="w-4 h-4 text-gray-500" />
                  </Button>
                </div>
              </div>

              <Button onClick={onClose} variant="outline" className="w-full hover:bg-gray-50 dark:hover:bg-gray-800">
                {t('done')}
              </Button>
            </div>
          )}

          {status === 'ERROR' && (
            <div className="space-y-5 text-center animate-in fade-in slide-in-from-bottom-4 duration-300">
              <div className="flex justify-center">
                <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-full">
                  <XCircle className="w-10 h-10 text-red-500" />
                </div>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-red-500">{t('failedTitle')}</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-2 bg-red-50 dark:bg-red-950/30 p-3 rounded-lg border border-red-100 dark:border-red-900/50">
                  {errorMsg}
                </p>
              </div>
              <Button
                onClick={() => setStatus('IDLE')}
                variant="outline"
                className="w-full hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-600 dark:hover:text-red-400 hover:border-red-200 dark:hover:border-red-900"
              >
                {t('tryAgain')}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default PublishModal;
