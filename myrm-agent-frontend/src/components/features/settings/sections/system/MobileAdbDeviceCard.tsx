'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest
 * - @/lib/utils/toast::toast
 * - next-intl::useTranslations
 *
 * [OUTPUT]
 * - MobileAdbDeviceCard: Android wireless debugging and device connection management panel.
 *
 * [POS]
 * Settings panel component for pairing and managing wireless Android devices.
 */

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Smartphone,
  CheckCircle2,
  XCircle,
  RefreshCw,
  QrCode,
  Wifi,
  Radio,
  Play,
  ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';
import { toast } from '@/lib/utils/toast';

interface MobileDeviceDto {
  device_id: string;
  host: string;
  port: int;
  model: string;
  state: string;
  is_wireless: boolean;
  screen_info?: {
    width: number;
    height: number;
    density_dpi: number;
  };
}

export const MobileAdbDeviceCard = memo(() => {
  const t = useTranslations('settings.mobileAdb');
  const [devices, setDevices] = useState<MobileDeviceDto[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPairing, setIsPairing] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);

  // Pairing form
  const [pairHost, setPairHost] = useState('192.168.');
  const [pairPort, setPairPort] = useState('');
  const [pairCode, setPairCode] = useState('');

  // Connect form
  const [connectHost, setConnectHost] = useState('192.168.');
  const [connectPort, setConnectPort] = useState('5555');

  const fetchDevices = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await apiRequest<{ devices: MobileDeviceDto[]; total: number }>({
        url: '/api/integrations/mobile-adb/devices',
        method: 'GET',
      });
      if (res.code === 200 && res.data) {
        setDevices(res.data.devices || []);
      }
    } catch (err) {
      // Ignore when offline
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const handlePair = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pairHost || !pairPort || !pairCode) {
      toast.error(t('fillAllFields'));
      return;
    }
    setIsPairing(true);
    try {
      const res = await apiRequest<{ message: string }>({
        url: '/api/integrations/mobile-adb/pair',
        method: 'POST',
        data: {
          host: pairHost.trim(),
          pairing_port: parseInt(pairPort.trim(), 10),
          pairing_code: pairCode.trim(),
        },
      });
      if (res.code === 200) {
        toast.success(t('pairSuccess'));
        setPairCode('');
        fetchDevices();
      } else {
        toast.error(res.message || t('pairFailed'));
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t('pairFailed'));
    } finally {
      setIsPairing(false);
    }
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!connectHost || !connectPort) {
      toast.error(t('fillAllFields'));
      return;
    }
    setIsConnecting(true);
    try {
      const res = await apiRequest<{ message: string }>({
        url: '/api/integrations/mobile-adb/connect',
        method: 'POST',
        data: {
          host: connectHost.trim(),
          port: parseInt(connectPort.trim(), 10),
        },
      });
      if (res.code === 200) {
        toast.success(t('connectSuccess'));
        fetchDevices();
      } else {
        toast.error(res.message || t('connectFailed'));
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t('connectFailed'));
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-border/50">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Smartphone className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold">{t('title')}</h3>
            <p className="text-xs text-muted-foreground">{t('description')}</p>
          </div>
        </div>
        <button
          onClick={() => fetchDevices()}
          disabled={isLoading}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-border hover:bg-muted/50 transition-colors"
          title={t('refresh')}
        >
          <RefreshCw className={cn('h-4 w-4 text-muted-foreground', isLoading && 'animate-spin')} />
        </button>
      </div>

      {/* Connected Devices List */}
      <div className="my-4">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          {t('activeDevices')} ({devices.length})
        </h4>
        {devices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 rounded-lg border border-dashed border-border/60 bg-muted/20 text-center">
            <Radio className="h-8 w-8 text-muted-foreground/40 mb-2 animate-pulse" />
            <p className="text-xs text-muted-foreground">{t('noDevicesFound')}</p>
            <p className="text-[11px] text-muted-foreground/70 mt-0.5">{t('pairPrompt')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {devices.map((d) => (
              <div
                key={d.device_id}
                className="flex items-center justify-between p-3 rounded-lg border border-border/80 bg-muted/30"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
                    <Wifi className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium">{d.model}</span>
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-500">
                        <CheckCircle2 className="h-3 w-3" />
                        {d.state}
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground font-mono mt-0.5">
                      {d.device_id} {d.screen_info ? `· ${d.screen_info.width}x${d.screen_info.height}` : ''}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pairing & Connect Forms */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-border/50">
        {/* Wireless Pairing */}
        <form onSubmit={handlePair} className="space-y-3 rounded-lg border border-border/60 p-3.5 bg-muted/10">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <QrCode className="h-4 w-4 text-primary" />
            {t('wirelessPairing')}
          </div>
          <div className="space-y-2">
            <div className="grid grid-cols-3 gap-2">
              <input
                type="text"
                placeholder="IP (192.168.1.X)"
                value={pairHost}
                onChange={(e) => setPairHost(e.target.value)}
                className="col-span-2 text-xs rounded-md border border-input bg-background px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <input
                type="text"
                placeholder="Port (37891)"
                value={pairPort}
                onChange={(e) => setPairPort(e.target.value)}
                className="col-span-1 text-xs rounded-md border border-input bg-background px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <input
              type="text"
              placeholder={t('pairingCodePlaceholder')}
              value={pairCode}
              onChange={(e) => setPairCode(e.target.value)}
              className="w-full text-xs rounded-md border border-input bg-background px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            type="submit"
            disabled={isPairing}
            className="w-full flex items-center justify-center gap-1.5 text-xs font-medium py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {isPairing ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />}
            {t('pairButton')}
          </button>
        </form>

        {/* Direct Connect */}
        <form onSubmit={handleConnect} className="space-y-3 rounded-lg border border-border/60 p-3.5 bg-muted/10">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <Wifi className="h-4 w-4 text-emerald-500" />
            {t('directConnect')}
          </div>
          <div className="space-y-2">
            <div className="grid grid-cols-3 gap-2">
              <input
                type="text"
                placeholder="IP (192.168.1.X)"
                value={connectHost}
                onChange={(e) => setConnectHost(e.target.value)}
                className="col-span-2 text-xs rounded-md border border-input bg-background px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <input
                type="text"
                placeholder="Port (5555)"
                value={connectPort}
                onChange={(e) => setConnectPort(e.target.value)}
                className="col-span-1 text-xs rounded-md border border-input bg-background px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={isConnecting}
            className="w-full flex items-center justify-center gap-1.5 text-xs font-medium py-1.5 rounded-md border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50"
          >
            {isConnecting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {t('connectButton')}
          </button>
        </form>
      </div>
    </div>
  );
});

MobileAdbDeviceCard.displayName = 'MobileAdbDeviceCard';
