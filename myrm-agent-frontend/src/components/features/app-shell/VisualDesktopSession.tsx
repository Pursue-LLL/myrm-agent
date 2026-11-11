/**
 * [INPUT]
 * - cp-sandbox (POS: 控制面：当前沙箱与其 VNC 地址)
 * - VisualDesktop (POS: VNC/noVNC 实时桌面嵌入视图，浏览器端按需加载)
 *
 * [OUTPUT]
 * VisualDesktopSession: 一次 VNC 会话。沙箱模式下挂载即取地址（连接中 → 桌面 / 加载失败 + 重连），本地模式直连本机桌面
 *
 * [POS]
 * VisualDesktopToggle 面板里的桌面区。一次会话就是一个组件实例：关闭面板或重连（父级换 key）都会整体重来，
 * 被放弃的会话迟到的回复不会落到新会话上。
 */

'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { buildVncWebSocketUrl, fetchSandboxVncUrl, fetchUserSandbox } from '@/lib/cp-sandbox';

const VisualDesktop = dynamic(() => import('./VisualDesktop').then((module) => ({ default: module.VisualDesktop })), {
  ssr: false,
});

const LOCAL_VNC_URL = 'ws://localhost:6080';

type VncTarget = { status: 'connecting' } | { status: 'ready'; wsUrl: string } | { status: 'failed' };

const CONNECTING: VncTarget = { status: 'connecting' };

/** A missing sandbox or VNC endpoint rejects: the panel shows a load failure with a reconnect action, never a blank view. */
async function fetchSandboxWsUrl(): Promise<string> {
  const sandbox = await fetchUserSandbox();
  if (!sandbox) {
    throw new Error('no_sandbox');
  }
  const vnc = await fetchSandboxVncUrl(sandbox.id);
  const wsUrl = buildVncWebSocketUrl(vnc.vnc_url, vnc.token);
  if (!wsUrl) {
    throw new Error('no_vnc_url');
  }
  return wsUrl;
}

export interface VisualDesktopSessionProps {
  sandboxMode: boolean;
  /** Watch only: mouse and keyboard stay local until the person takes control. */
  viewOnly: boolean;
  /** Asks the parent for a fresh session (it remounts this component). */
  onReconnect: () => void;
}

export const VisualDesktopSession = ({ sandboxMode, viewOnly, onReconnect }: VisualDesktopSessionProps) => {
  const t = useTranslations('billing.vnc');
  const [sandboxTarget, setSandboxTarget] = useState<VncTarget>(CONNECTING);

  // A reply to an abandoned session lands on an unmounted instance, which React ignores.
  useEffect(() => {
    if (!sandboxMode) {
      return;
    }
    void fetchSandboxWsUrl().then(
      (wsUrl) => setSandboxTarget({ status: 'ready', wsUrl }),
      () => setSandboxTarget({ status: 'failed' }),
    );
  }, [sandboxMode]);

  const target: VncTarget = sandboxMode ? sandboxTarget : { status: 'ready', wsUrl: LOCAL_VNC_URL };

  return (
    <div className="flex-1 relative bg-muted/30">
      {target.status === 'connecting' ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
          {t('connecting')}
        </div>
      ) : null}
      {target.status === 'failed' ? (
        <div className="absolute inset-0 flex flex-col gap-4 items-center justify-center px-6 text-center text-sm text-destructive-text">
          <p>{t('loadFailed')}</p>
          <button
            onClick={onReconnect}
            className="px-4 py-2 bg-primary text-primary-foreground font-medium rounded-lg hover:bg-primary/90 transition-colors"
          >
            {t('reconnect')}
          </button>
        </div>
      ) : null}
      {target.status === 'ready' ? (
        <VisualDesktop wsUrl={target.wsUrl} className="w-full h-full" onReconnect={onReconnect} viewOnly={viewOnly} />
      ) : null}
    </div>
  );
};
