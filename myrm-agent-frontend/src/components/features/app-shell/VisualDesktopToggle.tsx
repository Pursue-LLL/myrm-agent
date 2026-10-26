/**
 * [INPUT]
 * - useBrowserTakeoverStore (POS: 浏览器 HITL takeover 请求状态)
 * - useBrowserTakeoverActions (POS: Complete/Skip 与 VNC resume 同步)
 * - useUserControlStore (POS: 用户是否正在操作 Agent 的浏览器/桌面，接管与交还)
 * - VisualDesktop (POS: VNC/noVNC 实时桌面嵌入视图)
 *
 * [OUTPUT]
 * VisualDesktopToggle: managed 模式 VNC 浮动面板、接管/交还控制条与 HITL takeover 条
 *
 * [POS]
 * 沙箱/本地 VNC 桌面入口。面板默认仅查看；接管后才能点击/输入，期间 Agent 的浏览器与桌面工具暂停，交还后继续。
 * 关闭面板即交还（除非 Agent 正在等 Done/Skip）。extension 模式 takeover 由 ExtensionTakeoverBanner 处理，本组件不脉冲/不自动打开。
 */

'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { MonitorPlay, X, RefreshCw, CheckCircle2, XCircle, Eye, MousePointerClick, Undo2 } from 'lucide-react';
import { useFeatureEntitlements } from '@/hooks/billing/useFeatureEntitlements';
import { useBrowserTakeoverActions } from '@/hooks/approval/useBrowserTakeoverActions';
import { isSandbox } from '@/lib/deploy-mode';
import { buildVncWebSocketUrl, fetchSandboxVncUrl, fetchUserSandbox } from '@/lib/cp-sandbox';
import { cn } from '@/lib/utils/classnameUtils';
import { OPEN_VISUAL_DESKTOP_EVENT, type OpenVisualDesktopDetail } from '@/lib/visualDesktopEvents';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useUserControlStore from '@/store/useUserControlStore';

const VisualDesktop = dynamic(() => import('./VisualDesktop').then((module) => ({ default: module.VisualDesktop })), {
  ssr: false,
});

export const VisualDesktopToggle = () => {
  const t = useTranslations('billing.vnc');
  const [isOpen, setIsOpen] = useState(false);
  const [wsUrl, setWsUrl] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoadingUrl, setIsLoadingUrl] = useState(false);
  const { canUseVnc, isLoading: entitlementsLoading } = useFeatureEntitlements();
  const sandboxMode = isSandbox();
  const pending = useBrowserTakeoverStore((s) => s.pending);
  const uiMode = useBrowserTakeoverStore((s) => s.uiMode);
  const autoDetectCompletion = useBrowserTakeoverStore((s) => s.autoDetectCompletion);
  const takeoverReason = useBrowserTakeoverStore((s) => s.reason);
  const held = useUserControlStore((s) => s.held);
  const [controlBusy, setControlBusy] = useState(false);
  const managedTakeoverPending = pending && uiMode === 'managed';
  const awaitingUserAction = managedTakeoverPending && !autoDetectCompletion;
  const interactive = held || managedTakeoverPending;
  const { handleTakeoverComplete, handleTakeoverSkip } = useBrowserTakeoverActions();

  const takeControl = useCallback(async () => {
    setControlBusy(true);
    try {
      if (!(await useUserControlStore.getState().acquire('User took control'))) {
        toast.error(t('takeControlFailed'));
      }
    } finally {
      setControlBusy(false);
    }
  }, [t]);

  const handBack = useCallback(async (): Promise<boolean> => {
    setControlBusy(true);
    try {
      await useUserControlStore.getState().release();
      return true;
    } catch {
      toast.error(t('handBackFailed'));
      return false;
    } finally {
      setControlBusy(false);
    }
  }, [t]);

  // The agent waits for Done/Skip while a managed takeover is pending; closing the panel must not hand control back then.
  const shouldHandBackOnLeave = useCallback(() => {
    const takeover = useBrowserTakeoverStore.getState();
    return useUserControlStore.getState().held && !(takeover.pending && takeover.uiMode === 'managed');
  }, []);

  const closePanel = useCallback(async () => {
    if (shouldHandBackOnLeave() && !(await handBack())) {
      return;
    }
    setIsOpen(false);
  }, [handBack, shouldHandBackOnLeave]);

  useEffect(() => {
    if (managedTakeoverPending && !isOpen) {
      setIsOpen(true);
    }
  }, [managedTakeoverPending, isOpen]);

  useEffect(() => {
    const handleOpenVisualDesktop = (event: Event) => {
      setIsOpen(true);
      if ((event as CustomEvent<OpenVisualDesktopDetail>).detail?.takeover) {
        void takeControl();
      }
    };
    window.addEventListener(OPEN_VISUAL_DESKTOP_EVENT, handleOpenVisualDesktop);
    return () => {
      window.removeEventListener(OPEN_VISUAL_DESKTOP_EVENT, handleOpenVisualDesktop);
    };
  }, [takeControl]);

  useEffect(
    () => () => {
      if (shouldHandBackOnLeave()) {
        void useUserControlStore
          .getState()
          .release()
          .catch(() => undefined);
      }
    },
    [shouldHandBackOnLeave],
  );

  const loadVnc = useCallback(
    async (isMounted: { current: boolean }) => {
      setIsLoadingUrl(true);
      setLoadError(null);
      try {
        const sandbox = await fetchUserSandbox();
        if (!sandbox) {
          throw new Error('no_sandbox');
        }
        const vnc = await fetchSandboxVncUrl(sandbox.id);
        const url = buildVncWebSocketUrl(vnc.vnc_url, vnc.token);
        if (!url) {
          // A sandbox without a VNC endpoint is a load failure (message + reconnect), not a blank panel.
          throw new Error('no_vnc_url');
        }
        if (isMounted.current) {
          setWsUrl(url);
        }
      } catch {
        if (isMounted.current) {
          setLoadError(t('loadFailed'));
          setWsUrl('');
        }
      } finally {
        if (isMounted.current) {
          setIsLoadingUrl(false);
        }
      }
    },
    [t],
  );

  const handleReconnect = useCallback(() => {
    void loadVnc({ current: true });
  }, [loadVnc]);

  useEffect(() => {
    if (!isOpen || !sandboxMode) {
      return;
    }

    const isMounted = { current: true };
    void loadVnc(isMounted);

    return () => {
      isMounted.current = false;
    };
  }, [isOpen, sandboxMode, loadVnc]);

  if (sandboxMode && !entitlementsLoading && !canUseVnc) {
    return null;
  }

  const effectiveWsUrl = sandboxMode ? wsUrl : 'ws://localhost:6080';

  return (
    <>
      <button
        onClick={() => (isOpen ? void closePanel() : setIsOpen(true))}
        className={`fixed bottom-24 right-6 p-3 rounded-full shadow-lg transition-colors z-50 flex items-center justify-center max-sm:bottom-20 max-sm:right-4 ${managedTakeoverPending ? 'bg-amber-500 hover:bg-amber-600 text-white animate-pulse' : 'bg-primary text-primary-foreground hover:bg-primary/90'}`}
        title={managedTakeoverPending ? takeoverReason : t('toggleTitle')}
        aria-label={t('toggleTitle')}
      >
        <MonitorPlay size={24} />
      </button>

      {isOpen && (
        <div className="fixed bottom-36 right-6 w-[min(800px,calc(100vw-2rem))] h-[min(600px,calc(100vh-8rem))] bg-background rounded-xl shadow-2xl overflow-hidden z-50 border border-border flex flex-col max-sm:bottom-32 max-sm:right-4 max-sm:left-4">
          <div className="flex justify-between items-center px-4 py-2 bg-muted border-b border-border">
            <span className="text-foreground font-medium flex items-center gap-2 text-sm sm:text-base">
              <span className="w-2 h-2 rounded-full bg-destructive animate-pulse" />
              {t('panelTitle')}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleReconnect}
                className="text-muted-foreground hover:text-foreground"
                aria-label={t('reconnect')}
                title={t('reconnect')}
              >
                <RefreshCw size={16} />
              </button>
              <button
                onClick={() => void closePanel()}
                className="text-muted-foreground hover:text-foreground"
                aria-label={t('close')}
              >
                <X size={20} />
              </button>
            </div>
          </div>
          {!managedTakeoverPending && (
            <div
              data-testid="visual-desktop-control-bar"
              className={cn(
                'px-4 py-2 border-b flex items-center gap-3',
                held ? 'bg-primary/10 border-primary/20' : 'bg-muted/50 border-border',
              )}
            >
              {held ? (
                <span className="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" />
              ) : (
                <Eye size={14} className="text-muted-foreground shrink-0" />
              )}
              <p className="text-sm flex-1 min-w-0 truncate">
                <span className="font-medium text-foreground">{held ? t('inControl') : t('viewOnly')}</span>
                <span className="hidden sm:inline text-muted-foreground">
                  {' · '}
                  {held ? t('inControlHint') : t('viewOnlyHint')}
                </span>
              </p>
              <button
                onClick={() => void (held ? handBack() : takeControl())}
                disabled={controlBusy}
                data-testid={held ? 'visual-desktop-hand-back' : 'visual-desktop-take-control'}
                className={cn(
                  'shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors disabled:opacity-60',
                  held
                    ? 'bg-muted text-foreground hover:bg-muted/80'
                    : 'bg-primary text-primary-foreground hover:bg-primary/90',
                )}
              >
                {held ? <Undo2 size={14} /> : <MousePointerClick size={14} />}
                {held ? t('handBack') : t('takeControl')}
              </button>
            </div>
          )}
          {managedTakeoverPending && (
            <div className="px-4 py-2 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200 dark:border-amber-800 flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
              <p className="text-sm text-amber-800 dark:text-amber-200 flex-1 line-clamp-2">
                {autoDetectCompletion ? t('takeoverCaptchaAuto') : takeoverReason}
              </p>
              {awaitingUserAction ? (
                <div className="shrink-0 flex items-center gap-2">
                  <button
                    onClick={() => void handleTakeoverSkip()}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-muted text-muted-foreground rounded-md hover:bg-muted/80 transition-colors"
                  >
                    <XCircle size={14} />
                    {t('takeoverSkip')}
                  </button>
                  <button
                    onClick={() => void handleTakeoverComplete()}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
                  >
                    <CheckCircle2 size={14} />
                    {t('takeoverDone')}
                  </button>
                </div>
              ) : null}
            </div>
          )}
          <div className="flex-1 relative bg-muted/30">
            {sandboxMode && isLoadingUrl ? (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
                {t('connecting')}
              </div>
            ) : null}
            {sandboxMode && loadError ? (
              <div className="absolute inset-0 flex flex-col gap-4 items-center justify-center px-6 text-center text-sm text-destructive">
                <p>{loadError}</p>
                <button
                  onClick={handleReconnect}
                  className="px-4 py-2 bg-primary text-primary-foreground font-medium rounded hover:bg-primary/90 transition-colors"
                >
                  {t('reconnect')}
                </button>
              </div>
            ) : null}
            {!loadError && effectiveWsUrl && !isLoadingUrl ? (
              <VisualDesktop
                wsUrl={effectiveWsUrl}
                className="w-full h-full"
                onReconnect={handleReconnect}
                viewOnly={!interactive}
              />
            ) : null}
          </div>
        </div>
      )}
    </>
  );
};
