/**
 * [INPUT]
 * - @/hooks/useVoiceSession::VoiceSessionState (POS: Full-duplex voice session orchestrator)
 *
 * [OUTPUT]
 * - VoiceSessionOverlay: Full-screen voice session UI with waveform, state indicator, and barge-in.
 *
 * [POS]
 * Full-screen voice session overlay. Renders audio waveform visualization, session state,
 * interim transcripts, and interrupt controls for active voice conversations.
 */

'use client';

import { memo, useCallback, useEffect, useRef } from 'react';
import { Cancel01Icon, CallEnd01Icon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import type { VoiceSessionState, VoiceSessionMode } from '@/hooks/useVoiceSession';

interface VoiceSessionOverlayProps {
  isOpen: boolean;
  sessionState: VoiceSessionState;
  audioLevel: number;
  interimText: string;
  onClose: () => void;
  onInterrupt: () => void;
  agentResponseText?: string;
  agentToolName?: string;
  isAgentBridge?: boolean;
  voiceMode?: VoiceSessionMode;
}

const WAVEFORM_BARS = 24;
const WAVE_UPDATE_INTERVAL = 50;

function resolveThemeColor(el: HTMLElement): string {
  const raw = getComputedStyle(el).getPropertyValue('--primary').trim();
  if (!raw) return '59, 130, 246';
  if (raw.startsWith('#')) {
    const hex = raw.replace('#', '');
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    return `${r}, ${g}, ${b}`;
  }
  if (raw.startsWith('oklch') || raw.includes('%')) {
    const temp = document.createElement('div');
    temp.style.color = raw;
    document.body.appendChild(temp);
    const computed = getComputedStyle(temp).color;
    document.body.removeChild(temp);
    const match = computed.match(/\d+/g);
    if (match && match.length >= 3) return `${match[0]}, ${match[1]}, ${match[2]}`;
  }
  return raw;
}

function AudioWaveform({ level, active }: { level: number; active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef(0);
  const barsRef = useRef<number[]>(Array.from({ length: WAVEFORM_BARS }, () => 0));
  const colorRef = useRef('59, 130, 246');

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    colorRef.current = resolveThemeColor(canvas);

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let lastUpdate = 0;

    const draw = (timestamp: number) => {
      if (timestamp - lastUpdate > WAVE_UPDATE_INTERVAL) {
        lastUpdate = timestamp;

        const bars = barsRef.current;
        for (let i = 0; i < WAVEFORM_BARS; i++) {
          const targetHeight = active ? Math.max(0.05, level * (0.4 + Math.random() * 0.6)) : 0.03;
          bars[i] += (targetHeight - bars[i]) * 0.3;
        }
      }

      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.scale(dpr, dpr);

      ctx.clearRect(0, 0, w, h);

      const barWidth = (w / WAVEFORM_BARS) * 0.6;
      const gap = (w / WAVEFORM_BARS) * 0.4;
      const centerY = h / 2;
      const rgb = colorRef.current;

      barsRef.current.forEach((barHeight, i) => {
        const x = i * (barWidth + gap) + gap / 2;
        const halfBar = barHeight * centerY;

        const gradient = ctx.createLinearGradient(x, centerY - halfBar, x, centerY + halfBar);
        gradient.addColorStop(0, `rgba(${rgb}, 0.8)`);
        gradient.addColorStop(0.5, `rgba(${rgb}, 0.4)`);
        gradient.addColorStop(1, `rgba(${rgb}, 0.8)`);

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x, centerY - halfBar, barWidth, halfBar * 2, barWidth / 2);
        ctx.fill();
      });

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [level, active]);

  return <canvas ref={canvasRef} className="w-full h-24 sm:h-32" style={{ imageRendering: 'auto' }} />;
}

function StateIndicator({ state }: { state: VoiceSessionState }) {
  const t = useTranslations('voiceSession');

  const config = {
    inactive: { label: '', dotClass: '' },
    listening: { label: t('listening'), dotClass: 'bg-green-500 animate-pulse' },
    processing: { label: t('processing'), dotClass: 'bg-amber-500 animate-pulse' },
    speaking: { label: t('speaking'), dotClass: 'bg-primary animate-pulse' },
    paused: { label: '', dotClass: 'bg-gray-400' },
  };

  const { label, dotClass } = config[state];

  if (!label) return null;

  return (
    <div className="flex items-center gap-2">
      <span className={cn('w-2 h-2 rounded-full', dotClass)} />
      <span className="text-sm text-muted-foreground">{label}</span>
    </div>
  );
}

function ModeBadge({ mode }: { mode?: VoiceSessionMode }) {
  if (!mode) return null;

  const label = mode === 'openai_realtime' ? 'Realtime' : mode === 'agent_bridge' ? 'Agent Bridge' : 'Standard';

  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-muted/60 text-muted-foreground/80">
      {label}
    </span>
  );
}

const VoiceSessionOverlay = memo(
  ({
    isOpen,
    sessionState,
    audioLevel,
    interimText,
    onClose,
    onInterrupt,
    agentResponseText,
    agentToolName,
    isAgentBridge = false,
    voiceMode,
  }: VoiceSessionOverlayProps) => {
    const t = useTranslations('voiceSession');

    const handleCenterClick = useCallback(() => {
      if (sessionState === 'speaking') {
        onInterrupt();
      }
    }, [sessionState, onInterrupt]);

    if (!isOpen) return null;

    const isListening = sessionState === 'listening';
    const isSpeaking = sessionState === 'speaking';
    const isProcessing = sessionState === 'processing';

    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/95 backdrop-blur-md">
        {/* Close button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 sm:top-6 sm:right-6 p-2 rounded-full hover:bg-muted/50 transition-colors text-muted-foreground hover:text-foreground"
          aria-label="Close"
        >
          <Cancel01Icon size={20} />
        </button>

        {/* State indicator + mode badge */}
        <div className="mb-8 flex flex-col items-center gap-2">
          <StateIndicator state={sessionState} />
          <ModeBadge mode={voiceMode} />
        </div>

        {/* Audio waveform */}
        <div
          className={cn('w-64 sm:w-80 cursor-default transition-opacity', isSpeaking && 'cursor-pointer')}
          onClick={handleCenterClick}
          role={isSpeaking ? 'button' : undefined}
          tabIndex={isSpeaking ? 0 : undefined}
        >
          <AudioWaveform
            level={isListening ? audioLevel : isSpeaking ? 0.3 : 0.05}
            active={isListening || isSpeaking}
          />
        </div>

        {/* Interrupt hint during speaking */}
        {isSpeaking && <p className="mt-2 text-xs text-muted-foreground/50">{t('tapToInterrupt')}</p>}

        {/* Agent tool use indicator (agent_bridge mode) */}
        {isAgentBridge && agentToolName && isProcessing && (
          <div className="mt-3 flex items-center gap-2 px-4 py-1.5 rounded-full bg-muted/40">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            <span className="text-xs text-muted-foreground">{agentToolName}</span>
          </div>
        )}

        {/* Interim transcript + agent response */}
        <div className="mt-6 px-6 min-h-[2rem] max-w-md text-center">
          {interimText && <p className="text-sm text-muted-foreground animate-pulse">{interimText}</p>}
          {isProcessing && !interimText && !agentResponseText && (
            <div className="flex items-center justify-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:300ms]" />
            </div>
          )}
          {isAgentBridge && agentResponseText && (
            <p className="text-sm text-foreground/80 leading-relaxed line-clamp-4">{agentResponseText}</p>
          )}
        </div>

        {/* End session button */}
        <button
          type="button"
          onClick={onClose}
          className="mt-12 flex items-center gap-2 px-6 py-3 rounded-full bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
        >
          <CallEnd01Icon size={18} />
          <span className="text-sm font-medium">{t('stopSession')}</span>
        </button>
      </div>
    );
  },
);

VoiceSessionOverlay.displayName = 'VoiceSessionOverlay';

export default VoiceSessionOverlay;
