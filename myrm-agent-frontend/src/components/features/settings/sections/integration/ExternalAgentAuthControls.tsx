'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { IconLoader } from '@/components/features/icons/PremiumIcons';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import {
  feedExternalAgentLogin,
  importExternalAgentCredential,
  logoutExternalAgent,
  streamExternalAgentLogin,
  streamExternalAgentInstall,
  type ExternalAgentAuthEvent,
  type ExternalAgentAuthStatus,
} from '@/services/external-agents';

function newSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `login-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

interface InstallDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  command: string;
  onInstalled: () => void;
}

const InstallDialog = memo(({ open, onOpenChange, command, onInstalled }: InstallDialogProps) => {
  const t = useTranslations('settings.developer.externalAgents');
  const [events, setEvents] = useState<ExternalAgentAuthEvent[]>([]);
  const [installing, setInstalling] = useState(false);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setEvents([]);
    try {
      for await (const event of streamExternalAgentInstall(command)) {
        setEvents((prev) => [...prev, event]);
        if (event.type === 'success') {
          toast.success(t('installSuccess'));
          setTimeout(() => {
            onOpenChange(false);
            onInstalled();
          }, 1500);
        } else if (event.type === 'error') {
          toast.error(event.message);
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Installation failed');
    } finally {
      setInstalling(false);
    }
  }, [command, onOpenChange, onInstalled, t]);

  // Auto-start installation when opened
  useEffect(() => {
    if (open) {
      handleInstall();
    }
  }, [open, handleInstall]);

  return (
    <Dialog open={open} onOpenChange={(val) => !installing && onOpenChange(val)}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{t('installing', { backend: command })}</DialogTitle>
          <DialogDescription>{t('installingDesc')}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4 py-4">
          <div className="bg-muted text-muted-foreground flex max-h-[200px] flex-col gap-1 overflow-y-auto rounded-md p-4 font-mono text-xs">
            {events.map((ev, i) => (
              <div key={i} className={ev.type === 'error' ? 'text-destructive' : ev.type === 'success' ? 'text-green-500' : ''}>
                {ev.message}
              </div>
            ))}
            {installing && (
              <div className="flex items-center gap-2 text-blue-400">
                <IconLoader className="h-3 w-3 animate-spin" />
                <span>{t('installInProgress')}</span>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
});
InstallDialog.displayName = 'InstallDialog';

interface LoginDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  command: string;
  status: ExternalAgentAuthStatus;
  onChanged: () => void;
}

const LoginDialog = memo(({ open, onOpenChange, command, status, onChanged }: LoginDialogProps) => {
  const t = useTranslations('settings.developer.externalAgents');
  const [events, setEvents] = useState<ExternalAgentAuthEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [code, setCode] = useState('');
  const [importContent, setImportContent] = useState('');
  const [importing, setImporting] = useState(false);
  const sessionIdRef = useRef<string>('');
  const abortRef = useRef<AbortController | null>(null);
  const startedRef = useRef(false);
  const autoCloseRef = useRef<ReturnType<typeof setTimeout>>();

  const backend = status.backend;
  const scriptable = status.scriptableLogin;
  const needsCode = status.needsCodeInput;

  const startLogin = useCallback(async () => {
    setEvents([]);
    setRunning(true);
    const sessionId = newSessionId();
    sessionIdRef.current = sessionId;
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamExternalAgentLogin(
        { command, backend, sessionId },
        (event) => {
          setEvents((prev) => [...prev, event]);
          if (event.type === 'success') {
            toast.success(t('loginSuccess'));
            onChanged();
            autoCloseRef.current = setTimeout(() => onOpenChange(false), 1500);
          } else if (event.type === 'error') {
            toast.error(event.message || t('loginFailed'));
          }
        },
        controller.signal,
      );
    } catch {
      if (!controller.signal.aborted) {
        setEvents((prev) => [...prev, { type: 'error', message: t('loginFailed') }]);
      }
    } finally {
      setRunning(false);
    }
  }, [command, backend, t, onChanged, onOpenChange]);

  useEffect(() => {
    if (open && scriptable && !startedRef.current) {
      startedRef.current = true;
      void startLogin();
    }
    if (!open) {
      startedRef.current = false;
      abortRef.current?.abort();
      clearTimeout(autoCloseRef.current);
      setEvents([]);
      setCode('');
    }
  }, [open, scriptable, startLogin]);

  const handleSubmitCode = useCallback(async () => {
    const value = code.trim();
    if (!value) return;
    try {
      await feedExternalAgentLogin(sessionIdRef.current, value);
      setCode('');
    } catch {
      toast.error(t('loginFailed'));
    }
  }, [code, t]);

  const handleImport = useCallback(async () => {
    const content = importContent.trim();
    if (!content) return;
    setImporting(true);
    try {
      await importExternalAgentCredential(backend, content);
      toast.success(t('importSuccess'));
      setImportContent('');
      onChanged();
      onOpenChange(false);
    } catch {
      toast.error(t('loginFailed'));
    } finally {
      setImporting(false);
    }
  }, [backend, importContent, t, onChanged, onOpenChange]);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) abortRef.current?.abort();
      onOpenChange(next);
    },
    [onOpenChange],
  );

  const prompt = [...events].reverse().find((e) => e.type === 'prompt');
  const last = events[events.length - 1];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('loginTitle', { backend })}</DialogTitle>
          <DialogDescription>{t('authModeHint')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {scriptable ? (
            <div className="space-y-2">
              {running && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <IconLoader className="w-3.5 h-3.5 animate-spin" />
                  {last?.message || t('loginConnecting')}
                </div>
              )}
              {prompt?.url && (
                <div className="space-y-1.5 rounded-md border border-border p-3 text-sm">
                  <p className="text-muted-foreground">{t('loginOpenUrl')}</p>
                  <a href={prompt.url} target="_blank" rel="noreferrer" className="text-primary break-all underline">
                    {prompt.url}
                  </a>
                  {prompt.code && <p className="font-mono text-base tracking-widest">{prompt.code}</p>}
                </div>
              )}
              {needsCode && (
                <div className="flex items-end gap-2">
                  <div className="flex-1 space-y-1">
                    <label className="text-xs text-muted-foreground">{t('loginCode')}</label>
                    <Input
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      placeholder={t('loginCodePlaceholder')}
                    />
                  </div>
                  <Button size="sm" onClick={handleSubmitCode} disabled={!code.trim()}>
                    {t('loginCodeSubmit')}
                  </Button>
                </div>
              )}
              {last?.type === 'success' && (
                <p className="text-sm text-green-600 dark:text-green-400">{t('loginSuccess')}</p>
              )}
              {last?.type === 'error' && (
                <div className="flex items-center gap-2">
                  <p className="text-sm text-red-600 dark:text-red-400">{last.message}</p>
                  <Button variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={startLogin}>
                    {t('loginRetry')}
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-amber-600 dark:text-amber-400">{t('loginNotScriptable')}</p>
          )}

          <div className="space-y-1.5 border-t border-border pt-3">
            <label className="text-xs font-medium text-muted-foreground">{t('importTitle')}</label>
            <p className="text-[11px] text-muted-foreground/70">{t('importHint')}</p>
            <Textarea
              value={importContent}
              onChange={(e) => setImportContent(e.target.value)}
              placeholder={t('importPlaceholder')}
              rows={3}
              className="resize-none font-mono text-xs"
            />
            <div className="flex justify-end">
              <Button size="sm" variant="outline" onClick={handleImport} disabled={importing || !importContent.trim()}>
                {importing && <IconLoader className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
                {t('import')}
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => handleOpenChange(false)}>
            {t('loginClose')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});
LoginDialog.displayName = 'LoginDialog';

interface AuthControlsProps {
  command: string;
  status: ExternalAgentAuthStatus | null;
  onChanged: () => void;
}

/** Per-agent subscription-auth controls: login-state badge + login / logout actions. */
const ExternalAgentAuthControls = memo(({ command, status, onChanged }: AuthControlsProps) => {
  const t = useTranslations('settings.developer.externalAgents');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [installDialogOpen, setInstallDialogOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = useCallback(async () => {
    if (!status) return;
    setLoggingOut(true);
    try {
      await logoutExternalAgent(status.backend);
      toast.success(t('logoutSuccess'));
      onChanged();
    } catch {
      toast.error(t('loginFailed'));
    } finally {
      setLoggingOut(false);
    }
  }, [status, t, onChanged]);

  if (!status) return null;

  if (!status.installed) {
    return (
      <>
        <Button variant="outline" size="sm" onClick={() => setInstallDialogOpen(true)}>
          {t('install')}
        </Button>
        <InstallDialog
          open={installDialogOpen}
          onOpenChange={setInstallDialogOpen}
          command={status.backend}
          onInstalled={onChanged}
        />
      </>
    );
  }

  return (
    <>
      <div className="flex items-center gap-1.5">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
            status.authenticated
              ? 'bg-green-500/10 text-green-600 dark:text-green-400'
              : 'bg-muted text-muted-foreground'
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${status.authenticated ? 'bg-green-500' : 'bg-muted-foreground/40'}`}
          />
          {status.authenticated ? t('badgeLoggedIn') : t('badgeLoggedOut')}
        </span>
        {status.authenticated ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[11px]"
            onClick={handleLogout}
            disabled={loggingOut}
          >
            {loggingOut && <IconLoader className="w-3 h-3 mr-1 animate-spin" />}
            {t('logout')}
          </Button>
        ) : (
          <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px]" onClick={() => setDialogOpen(true)}>
            {t('login')}
          </Button>
        )}
      </div>
      <LoginDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        command={command}
        status={status}
        onChanged={onChanged}
      />
    </>
  );
});
ExternalAgentAuthControls.displayName = 'ExternalAgentAuthControls';

export default ExternalAgentAuthControls;
