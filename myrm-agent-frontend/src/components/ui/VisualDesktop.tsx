'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

interface VisualDesktopProps {
  wsUrl: string;
  className?: string;
  onReconnect?: () => void;
}

type NoVNCClient = {
  addEventListener: (type: 'connect' | 'disconnect', listener: () => void) => void;
  disconnect: () => void;
  scaleViewport: boolean;
  resizeSession: boolean;
};

export const VisualDesktop: React.FC<VisualDesktopProps> = ({ wsUrl, className, onReconnect }) => {
  const t = useTranslations('billing.vnc');
  const containerRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<NoVNCClient | null>(null);
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');

  useEffect(() => {
    if (!containerRef.current) return;

    let mounted = true;

    const initRFB = async () => {
      try {
        const { default: RFB } = await import('@novnc/novnc');

        if (!mounted || !containerRef.current) return;

        rfbRef.current = new RFB(containerRef.current, wsUrl, {
          credentials: { password: '' },
        }) as NoVNCClient;

        rfbRef.current.addEventListener('connect', () => {
          if (mounted) setStatus('connected');
        });
        rfbRef.current.addEventListener('disconnect', () => {
          if (mounted) setStatus('disconnected');
        });

        rfbRef.current.scaleViewport = true;
        rfbRef.current.resizeSession = true;
      } catch (err) {
        console.error('Failed to initialize noVNC:', err);
        if (mounted) setStatus('disconnected');
      }
    };

    initRFB();

    return () => {
      mounted = false;
      if (rfbRef.current) {
        rfbRef.current.disconnect();
      }
    };
  }, [wsUrl]);

  return (
    <div className={`relative bg-black rounded-lg overflow-hidden flex items-center justify-center ${className ?? ''}`}>
      {status !== 'connected' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80 text-white z-10">
          <div className="flex flex-col items-center gap-2 px-4 text-center">
            {status === 'connecting' ? (
              <>
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <span className="text-sm">{t('connecting')}</span>
              </>
            ) : (
              <>
                <span className="text-sm text-destructive">{t('disconnected')}</span>
                {onReconnect ? (
                  <button
                    onClick={onReconnect}
                    className="mt-2 px-3 py-1.5 bg-primary text-primary-foreground text-xs font-medium rounded hover:bg-primary/90 transition-colors"
                  >
                    {t('reconnect')}
                  </button>
                ) : (
                  <span className="text-xs text-white/60">{t('disconnectedHint')}</span>
                )}
              </>
            )}
          </div>
        </div>
      )}
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
};
