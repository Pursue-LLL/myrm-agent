'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

interface HoldToApproveButtonProps {
  onTrigger: () => void;
  disabled?: boolean;
  label: string;
  durationMs?: number;
  className?: string;
}

export const HoldToApproveButton: React.FC<HoldToApproveButtonProps> = ({
  onTrigger,
  disabled = false,
  label,
  durationMs = 700,
  className,
}) => {
  const [progress, setProgress] = useState(0);
  const [isPressing, setIsPressing] = useState(false);
  const startTimeRef = useRef<number | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const triggeredRef = useRef(false);

  const cancelPress = useCallback(() => {
    setIsPressing(false);
    setProgress(0);
    startTimeRef.current = null;
    triggeredRef.current = false;
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
  }, []);

  const startPress = useCallback(() => {
    if (disabled) return;
    setIsPressing(true);
    triggeredRef.current = false;
    startTimeRef.current = Date.now();

    const tick = () => {
      if (!startTimeRef.current) return;
      const elapsed = Date.now() - startTimeRef.current;
      const pct = Math.min(100, (elapsed / durationMs) * 100);
      setProgress(pct);

      if (pct >= 100) {
        if (!triggeredRef.current) {
          triggeredRef.current = true;
          onTrigger();
        }
        cancelPress();
      } else {
        animFrameRef.current = requestAnimationFrame(tick);
      }
    };

    animFrameRef.current = requestAnimationFrame(tick);
  }, [disabled, durationMs, onTrigger, cancelPress]);

  useEffect(() => {
    return () => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, []);

  return (
    <button
      type="button"
      onPointerDown={startPress}
      onPointerUp={cancelPress}
      onPointerLeave={cancelPress}
      onContextMenu={(e) => e.preventDefault()}
      disabled={disabled}
      className={cn(
        'relative overflow-hidden select-none touch-none',
        'h-7 px-2.5 text-xs font-medium rounded-lg border transition-colors',
        'bg-primary/10 border-primary/30 text-primary hover:bg-primary/20',
        'disabled:opacity-50 disabled:pointer-events-none',
        isPressing && 'scale-[0.98]',
        className,
      )}
      title={label}
    >
      {/* Background progress fill */}
      <span
        className="absolute inset-0 bg-primary/30 transition-all pointer-events-none"
        style={{
          width: `${progress}%`,
          transition: isPressing ? 'none' : 'width 150ms ease-out',
        }}
      />
      <span className="relative z-10 flex items-center gap-1.5">
        <ShieldCheck className="h-3.5 w-3.5" />
        <span>{label}</span>
      </span>
    </button>
  );
};
