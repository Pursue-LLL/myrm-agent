'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Loader2, Globe, CheckCircle2, XCircle, Copy, ExternalLink } from 'lucide-react';
import { Artifact } from '@/store/chat/types';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { getApiUrl } from '@/lib/api';
import { useTranslations } from 'next-intl';

export interface DeployedArtifactUpdate {
  deployment_url: string;
  deployment_status: string;
  deployment_project_id?: string | null;
}

interface DeployModalProps {
  artifact: Artifact;
  open: boolean;
  onClose: () => void;
  onDeployed?: (update: DeployedArtifactUpdate) => void;
}

const CREDENTIALS_URL = '/api/v1/files/artifacts/deploy/credentials/vercel';
const LEGACY_TOKEN_KEY = 'vercel_token';

export const DeployModal: React.FC<DeployModalProps> = ({ artifact, open, onClose, onDeployed }) => {
  const t = useTranslations('artifacts.deploy');
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<'IDLE' | 'DEPLOYING' | 'SUCCESS' | 'ERROR'>('IDLE');
  const [logs, setLogs] = useState<string[]>([]);
  const [deployUrl, setDeployUrl] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [copied, setCopied] = useState(false);
  const [credentialsLoading, setCredentialsLoading] = useState(false);
  const isIntentionalClose = useRef(false);

  const notifyDeployed = useCallback(
    (url: string, deploymentStatus: string, projectId?: string | null) => {
      onDeployed?.({
        deployment_url: url,
        deployment_status: deploymentStatus,
        deployment_project_id: projectId ?? null,
      });
    },
    [onDeployed],
  );

  const saveCredentials = useCallback(async (value: string) => {
    const response = await fetch(getApiUrl(CREDENTIALS_URL), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: value }),
    });
    if (!response.ok) {
      throw new Error(t('errors.saveCredentialsFailed'));
    }
  }, [t]);

  useEffect(() => {
    if (!open) {
      return;
    }

    setStatus('IDLE');
    setLogs([]);
    setDeployUrl('');
    setErrorMsg('');
    setCopied(false);
    isIntentionalClose.current = false;

    let cancelled = false;

    const loadCredentials = async () => {
      setCredentialsLoading(true);
      try {
        const response = await fetch(getApiUrl(CREDENTIALS_URL));
        if (response.ok) {
          const data = (await response.json()) as { token?: string | null; configured?: boolean };
          if (!cancelled && data.token) {
            setToken(data.token);
            return;
          }
        }

        const legacyToken = localStorage.getItem(LEGACY_TOKEN_KEY);
        if (legacyToken && !cancelled) {
          await saveCredentials(legacyToken);
          localStorage.removeItem(LEGACY_TOKEN_KEY);
          setToken(legacyToken);
        }
      } catch (error) {
        console.error('Failed to load Vercel credentials:', error);
      } finally {
        if (!cancelled) {
          setCredentialsLoading(false);
        }
      }
    };

    void loadCredentials();

    return () => {
      cancelled = true;
    };
  }, [open, saveCredentials]);

  const handleDeploy = async () => {
    if (!token.trim()) {
      setErrorMsg(t('errors.tokenRequired'));
      return;
    }

    try {
      await saveCredentials(token.trim());
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('errors.saveCredentialsFailed');
      setErrorMsg(message);
      return;
    }

    setStatus('DEPLOYING');
    setLogs([t('logs.initiating')]);
    setErrorMsg('');
    isIntentionalClose.current = false;

    try {
      const response = await fetch(getApiUrl(`/api/v1/files/artifacts/${artifact.id}/deploy`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: token.trim(), platform: 'vercel' }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || t('errors.deployFailed'));
      }

      const data = await response.json();
      const deploymentId = data.deployment_id as string | undefined;
      const initialUrl = typeof data.url === 'string' ? data.url : '';

      if (initialUrl) {
        setDeployUrl(initialUrl);
        notifyDeployed(initialUrl, typeof data.status === 'string' ? data.status : 'DEPLOYING', data.project_id);
      }

      if (!deploymentId) {
        throw new Error(t('errors.noDeploymentId'));
      }

      setLogs((prev) => [...prev, t('logs.created', { id: deploymentId }), t('logs.connecting')]);

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = getApiUrl('').replace(/^https?:\/\//, '');
      const wsUrl = `${wsProtocol}//${wsHost}/api/v1/files/artifacts/${artifact.id}/deploy/status/${deploymentId}`;

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token: token.trim() }));
      };

      ws.onmessage = (event) => {
        const statusData = JSON.parse(event.data) as { status?: string; url?: string; project_id?: string };
        const currentStatus = statusData.status ?? 'UNKNOWN';

        setLogs((prev) => [...prev, t('logs.status', { status: currentStatus })]);

        if (currentStatus === 'READY') {
          const url = statusData.url ?? initialUrl;
          setStatus('SUCCESS');
          setDeployUrl(url);
          notifyDeployed(url, 'READY', statusData.project_id);
          isIntentionalClose.current = true;
          ws.close();
        } else if (currentStatus === 'ERROR' || currentStatus === 'CANCELED') {
          setStatus('ERROR');
          setErrorMsg(t('errors.deploymentStatus', { status: currentStatus.toLowerCase() }));
          isIntentionalClose.current = true;
          ws.close();
        }
      };

      ws.onclose = () => {
        setStatus((currentStatus) => {
          if (currentStatus === 'DEPLOYING' && !isIntentionalClose.current) {
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
    if (!deployUrl) return;
    try {
      await writeToClipboard(deployUrl);
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
              <div className="space-y-2">
                <Label htmlFor="token" className="text-sm font-medium">
                  {t('tokenLabel')}
                </Label>
                <Input
                  id="token"
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder={t('tokenPlaceholder')}
                  disabled={credentialsLoading}
                  className="w-full font-mono text-sm bg-gray-50 dark:bg-gray-950 border-gray-200 dark:border-gray-800 focus-visible:ring-primary"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {t('tokenHint')}{' '}
                  <a
                    href="https://vercel.com/account/tokens"
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    {t('tokenLink')}
                  </a>
                  .
                </p>
              </div>
              {errorMsg && (
                <p className="text-sm text-red-500 bg-red-50 dark:bg-red-950/50 p-2 rounded-md border border-red-100 dark:border-red-900">
                  {errorMsg}
                </p>
              )}
              <Button
                onClick={handleDeploy}
                className="w-full shadow-lg shadow-primary/20 transition-all hover:scale-[1.02]"
                disabled={!token.trim() || credentialsLoading}
              >
                {t('deployNow')}
              </Button>
            </div>
          )}

          {status === 'DEPLOYING' && (
            <div className="space-y-5 animate-in fade-in zoom-in-95 duration-300">
              <div className="flex flex-col items-center justify-center py-6 gap-4">
                <div className="relative">
                  <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
                  <Loader2 className="w-10 h-10 animate-spin text-primary relative z-10" />
                </div>
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300 animate-pulse">
                  {t('deploying')}
                </p>
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
                  value={deployUrl}
                  readOnly
                  className="bg-transparent border-none focus-visible:ring-0 font-mono text-sm text-primary"
                />
                <div className="flex gap-1 pr-1">
                  <Button size="icon" variant="ghost" onClick={handleCopy} className="hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg">
                    {copied ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4 text-gray-500" />}
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => window.open(deployUrl, '_blank')}
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
