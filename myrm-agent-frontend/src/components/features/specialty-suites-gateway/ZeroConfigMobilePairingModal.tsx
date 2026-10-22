/**
 * [INPUT] isOpen, onClose, channel options
 * [OUTPUT] ZeroConfigMobilePairingModal component for 1-second mobile companion connection
 * [POS] specialty-suites-gateway/ZeroConfigMobilePairingModal.tsx
 */

'use client';

import React, { useEffect } from 'react';
import {
  QrCode,
  RefreshCw,
  Smartphone,
  ShieldCheck,
  CheckCircle2,
  X,
  Key,
  CloudLightning,
} from 'lucide-react';
import type { ConnectorChannel } from './specialtyGatewayTypes';
import { useMobilePairingQrGateway } from './useMobilePairingQrGateway';

export interface ZeroConfigMobilePairingModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultChannel?: ConnectorChannel;
  className?: string;
}

const CHANNELS_CONFIG: { id: ConnectorChannel; name: string }[] = [
  { id: 'feishu', name: '飞书' },
  { id: 'wechat_work', name: '企业微信' },
  { id: 'dingtalk', name: '钉钉' },
  { id: 'telegram', name: 'Telegram' },
];

export const ZeroConfigMobilePairingModal: React.FC<ZeroConfigMobilePairingModalProps> = ({
  isOpen,
  onClose,
  defaultChannel = 'feishu',
  className = '',
}) => {
  const {
    activeChannel,
    session,
    companion,
    remainingSeconds,
    initiatePairing,
    refreshQr,
    disconnectCompanion,
    simulateScanAndAuth,
  } = useMobilePairingQrGateway({ defaultChannel });

  useEffect(() => {
    if (isOpen && !session && !companion) {
      initiatePairing(defaultChannel);
    }
  }, [isOpen, session, companion, defaultChannel, initiatePairing]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const isExpired = session?.stage === 'expired';
  const isAuthenticated = session?.stage === 'authenticated' || Boolean(companion);

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="mobile-pairing-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto m-0 h-full w-full max-w-none max-h-none border-0 animate-in fade-in duration-150"
    >
      <div
        className={`w-full max-w-md rounded-2xl border border-border/80 bg-card text-card-foreground shadow-2xl overflow-hidden flex flex-col ${className}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-4 bg-muted/20">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
              <Smartphone className="h-5 w-5" />
            </div>
            <div>
              <h3
                id="mobile-pairing-title"
                className="text-sm font-semibold text-foreground tracking-tight"
              >
                免配置移动伴侣扫码网关
              </h3>
              <p className="text-[11px] text-muted-foreground">
                1 秒扫码即连 · 通勤随身接管 · 离线云端中继
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="关闭扫码弹窗"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Channel Selector Tabs */}
        {!isAuthenticated && (
          <div className="flex items-center gap-1 border-b px-5 py-2.5 bg-muted/10">
            {CHANNELS_CONFIG.map((ch) => {
              const isSelected = ch.id === activeChannel;
              return (
                <button
                  key={ch.id}
                  type="button"
                  onClick={() => {
                    initiatePairing(ch.id);
                  }}
                  className={`flex-1 rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                    isSelected
                      ? 'bg-primary text-primary-foreground shadow-xs'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                >
                  {ch.name}
                </button>
              );
            })}
          </div>
        )}

        {/* Content Body */}
        <div className="p-6 flex flex-col items-center justify-center text-center space-y-4">
          {isAuthenticated ? (
            /* Paired State */
            <div className="w-full space-y-4 py-2">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                <CheckCircle2 className="h-7 w-7" />
              </div>

              <div className="space-y-1">
                <h4 className="text-sm font-semibold text-foreground">移动伴侣已安全绑定</h4>
                <p className="text-xs text-muted-foreground">
                  已与 {session?.deviceLabel || '移动终端'} 建立端到端加密通道
                </p>
              </div>

              <div className="rounded-xl border border-border/70 bg-muted/30 p-3.5 text-left space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground flex items-center gap-1.5">
                    <CloudLightning className="h-3.5 w-3.5 text-primary" />
                    离线云端中继：
                  </span>
                  <span className="rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 text-[10px] font-semibold">
                    已开启 · 随走随用
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
                    会话密钥状态：
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    Ed25519 活跃
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={disconnectCompanion}
                className="w-full rounded-xl border border-destructive/30 bg-destructive/5 hover:bg-destructive/10 text-destructive text-xs font-medium py-2 transition-colors"
              >
                解绑当前伴侣设备
              </button>
            </div>
          ) : isExpired ? (
            /* Expired State */
            <div className="w-full space-y-4 py-4">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-destructive/10 text-destructive border border-destructive/20">
                <RefreshCw className="h-6 w-6" />
              </div>
              <div className="space-y-1">
                <h4 className="text-sm font-semibold text-foreground">二维码已失效</h4>
                <p className="text-xs text-muted-foreground">
                  为保障会话安全，临时握手二维码已超时过期
                </p>
              </div>
              <button
                type="button"
                onClick={refreshQr}
                className="inline-flex items-center justify-center gap-1.5 w-full rounded-xl bg-primary text-primary-foreground text-xs font-semibold py-2.5 shadow-xs hover:bg-primary/90 transition-colors"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>重新生成配对二维码</span>
              </button>
            </div>
          ) : (
            /* Waiting Scan State */
            <div className="w-full space-y-4">
              <div className="relative mx-auto flex h-48 w-48 items-center justify-center rounded-2xl border border-border/80 bg-white p-3 shadow-inner">
                {/* Visual QR Code Display Container */}
                <div
                  data-testid="mock-qr-code"
                  className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-lg bg-neutral-900 text-white p-3 font-mono text-[10px]"
                >
                  <QrCode className="h-20 w-20 text-white" />
                  <span className="text-neutral-400">扫码连接 {activeChannel}</span>
                </div>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-center gap-2">
                  <span className="text-xs font-medium text-foreground">
                    打开手机 App 扫描上方二维码
                  </span>
                  <span className="rounded bg-primary/10 text-primary font-mono text-[10px] px-1.5 py-0.5">
                    {remainingSeconds}s
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground flex items-center justify-center gap-1">
                  <Key className="h-3 w-3" />
                  <span>临时密钥: {session?.ephemeralPublicKey || 'ed25519-generating'}</span>
                </p>
              </div>

              {/* Companion Simulation Button (Non-production or automated verification) */}
              {process.env.NODE_ENV !== 'production' && (
                <button
                  type="button"
                  data-testid="simulate-scan-auth-btn"
                  onClick={() => {
                    simulateScanAndAuth();
                  }}
                  className="text-[11px] text-muted-foreground hover:text-primary transition-colors underline"
                >
                  测试伴侣设备一键联通
                </button>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end border-t px-5 py-3 bg-muted/20">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border px-3.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            完成
          </button>
        </div>
      </div>
    </dialog>
  );
};
