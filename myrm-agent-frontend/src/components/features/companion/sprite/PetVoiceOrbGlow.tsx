/**
 * [INPUT]
 * - ./petSurfaceTypes::PetSurfaceVoiceState (POS: IPC voice state type)
 *
 * [OUTPUT]
 * - PetVoiceOrbGlow: Visual voice halo glow layer for pet companion
 *
 * [POS]
 * Independent halo glow ripple layer for pet surface. Explicitly sets pointer-events: none
 * to isolate from pixel-level alpha sampling and prevent mouse event interception.
 */

'use client';

import { memo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { PetSurfaceVoiceState } from './petSurfaceTypes';

interface PetVoiceOrbGlowProps {
  voiceState?: PetSurfaceVoiceState;
  audioLevel?: number;
  size: number;
}

/**
 * PetVoiceOrbGlow — 独立的光晕波纹层。
 * 显式设置 pointer-events: none，与像素级 Alpha 穿透采样彻底解耦，杜绝鼠标穿透误拦截。
 */
export const PetVoiceOrbGlow = memo(function PetVoiceOrbGlow({
  voiceState = 'idle',
  audioLevel = 0,
  size,
}: PetVoiceOrbGlowProps) {
  if (voiceState === 'idle') {
    return null;
  }

  const scale = 1 + Math.min(0.4, audioLevel * 0.8);
  const isListening = voiceState === 'listening';
  const isSpeaking = voiceState === 'speaking';
  const isProcessing = voiceState === 'processing';

  return (
    <div
      className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center select-none"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <div
        className={cn(
          'absolute rounded-full transition-all duration-150',
          isListening && 'bg-blue-500/20 shadow-[0_0_24px_rgba(59,130,246,0.5)] animate-pulse',
          isSpeaking && 'bg-emerald-500/25 shadow-[0_0_28px_rgba(16,185,129,0.6)]',
          isProcessing && 'bg-purple-500/20 shadow-[0_0_20px_rgba(168,85,247,0.5)] animate-spin',
        )}
        style={{
          width: size * 1.1,
          height: size * 1.1,
          transform: `scale(${scale})`,
        }}
      />
    </div>
  );
});

export default PetVoiceOrbGlow;
