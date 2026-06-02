'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { IconLoader, IconRefresh, IconWifi, IconWifiOff } from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { WhatsAppStatus } from '@/services/channels';
import { startLogin, subscribeLoginStream, cancelLogin } from '@/services/channels';
import { type LoginEvent, LoginStatus } from '@/types/channels';

export interface WhatsAppCardProps {
  waStatus: WhatsAppStatus | null;
  loading: boolean;
  onRefresh: () => void;
  t: (key: string) => string;
}

export function WhatsAppCard({ waStatus, loading, onRefresh, t }: WhatsAppCardProps) {
  const [sseQrCode, setSseQrCode] = useState<string | null>(null);
  const [sseStatus, setSseStatus] = useState<'pending' | 'success' | 'failed' | null>(null);
  const [connecting, setConnecting] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sseStatusRef = useRef(sseStatus);
  sseStatusRef.current = sseStatus;

  useEffect(() => {
    if (waStatus?.connected) {
      setSseQrCode(null);
      setSseStatus(null);
      setConnecting(false);
    }
  }, [waStatus?.connected]);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      if (sessionIdRef.current && sseStatusRef.current !== 'success') {
        cancelLogin(sessionIdRef.current).catch(() => {});
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConnect = useCallback(async () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    if (sessionIdRef.current) {
      cancelLogin(sessionIdRef.current).catch(() => {});
      sessionIdRef.current = null;
    }

    setConnecting(true);
    setSseStatus('pending');
    setSseQrCode(null);

    try {
      const res = await startLogin('whatsapp', 'qr_code');
      sessionIdRef.current = res.session_id;

      eventSourceRef.current = subscribeLoginStream(
        res.session_id,
        (event: LoginEvent) => {
          const { status } = event.state;
          if (status === LoginStatus.SUCCESS) {
            setSseStatus('success');
            setConnecting(false);
            onRefresh();
          } else if (
            status === LoginStatus.FAILED ||
            status === LoginStatus.TIMEOUT ||
            status === LoginStatus.CANCELLED
          ) {
            setSseStatus('failed');
            setConnecting(false);
          }
          if (event.state.qr_code_base64) {
            setSseQrCode(`data:image/png;base64,${event.state.qr_code_base64}`);
          }
        },
        () => {
          setSseStatus('failed');
          setConnecting(false);
        },
      );
    } catch {
      setSseStatus('failed');
      setConnecting(false);
    }
  }, [onRefresh]);

  if (loading && !waStatus) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
      </div>
    );
  }

  const isConnected = waStatus?.connected || sseStatus === 'success';
  const displayQrCode = sseQrCode || waStatus?.qr_code;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-lg border bg-card px-4 py-3">
        <div className="flex items-center gap-3">
          {isConnected ? (
            <IconWifi className="h-4 w-4 text-green-500" />
          ) : (
            <IconWifiOff className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="text-sm font-medium">WhatsApp</span>
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium leading-tight',
              isConnected
                ? 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20'
                : 'bg-muted text-muted-foreground border-muted',
            )}
          >
            <span className={cn('h-1.5 w-1.5 rounded-full', isConnected ? 'bg-green-500' : 'bg-muted-foreground/50')} />
            {isConnected ? t('whatsappConnected') : t('whatsappDisconnected')}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {!isConnected && !connecting && (
            <Button variant="ghost" size="sm" className="h-7 text-xs px-2" onClick={handleConnect}>
              {t('wechatTriggerLogin')}
            </Button>
          )}
          {connecting && !displayQrCode && (
            <Button variant="ghost" size="sm" className="h-7 text-xs px-2" disabled>
              <IconLoader className="h-3 w-3 animate-spin mr-1" />
              {t('wechatLoggingIn')}
            </Button>
          )}
          {isConnected && (
            <Button variant="ghost" size="sm" className="h-7 text-xs px-2" onClick={handleConnect}>
              {t('wechatReLogin')}
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onRefresh}>
            <IconRefresh className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {isConnected && waStatus?.phone_number && (
        <div className="rounded-lg border bg-card px-4 py-3">
          <p className="text-sm text-muted-foreground">
            {t('whatsappPhoneNumber')}:{' '}
            <span className="font-mono font-medium text-foreground">+{waStatus.phone_number}</span>
          </p>
        </div>
      )}

      {!isConnected && displayQrCode && (
        <div className="rounded-lg border bg-card p-4 text-center space-y-3">
          <p className="text-sm text-muted-foreground">{t('whatsappScanQR')}</p>
          <div className="inline-block bg-white p-4 rounded-lg">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={displayQrCode} alt="WhatsApp QR Code" className="w-48 h-48" />
          </div>
        </div>
      )}

      {!isConnected && !displayQrCode && sseStatus === 'failed' && (
        <div className="text-center py-3 space-y-2">
          <p className="text-xs text-muted-foreground">{t('whatsappServiceUnavailable')}</p>
          <Button variant="outline" size="sm" onClick={handleConnect} className="text-xs">
            <IconRefresh className="h-3 w-3 mr-1" />
            {t('retry')}
          </Button>
        </div>
      )}
    </div>
  );
}
