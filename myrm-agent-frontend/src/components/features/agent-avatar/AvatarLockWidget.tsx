'use client';

/**
 * Avatar Display & Lock/Fine-Tune Widget Component.
 *
 * [INPUT] metadata: AvatarMetadata, onToggleLock, onRollSeed, onChangeStyle, onChangeBgColor
 * [OUTPUT] AvatarLockWidget: Compact interactive widget with SVG render, lock switch, style tabs, and color palette.
 * [POS] src/components/features/agent-avatar/AvatarLockWidget.tsx
 */

import { memo } from 'react';
import { Lock, Unlock, Palette, Sparkles, Check } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  AVATAR_COLOR_PRESETS,
  type AvatarMetadata,
  type AvatarStyle,
} from './avatarTypes';
import { DiceRollButton } from './DiceRollButton';

export interface AvatarLockWidgetProps {
  metadata: AvatarMetadata;
  onToggleLock: () => void;
  onRollSeed: (newSeed: string) => void;
  onChangeStyle?: (newStyle: AvatarStyle) => void;
  onChangeBgColor?: (newColor: string) => void;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const STYLE_OPTIONS: Array<{ key: AvatarStyle; labelKey: string; defaultLabel: string }> = [
  { key: 'beam', labelKey: 'styleBeam', defaultLabel: 'Beam' },
  { key: 'pixel', labelKey: 'stylePixel', defaultLabel: 'Pixel' },
  { key: 'cyberpunk', labelKey: 'styleCyberpunk', defaultLabel: 'Cyber' },
  { key: 'bauhaus', labelKey: 'styleBauhaus', defaultLabel: 'Bauhaus' },
];

export const AvatarLockWidget = memo(function AvatarLockWidget({
  metadata,
  onToggleLock,
  onRollSeed,
  onChangeStyle,
  onChangeBgColor,
  className,
  size = 'md',
}: AvatarLockWidgetProps) {
  const t = useTranslations('agentAvatar');

  const avatarBoxSizes = {
    sm: 'w-20 h-20',
    md: 'w-28 h-28',
    lg: 'w-36 h-36',
  }[size];

  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 p-4 rounded-xl border border-border bg-card/80 backdrop-blur-sm shadow-sm',
        className,
      )}
      data-testid="avatar-lock-widget"
    >
      {/* Avatar Container with Floating Lock Badge */}
      <div className="relative group select-none">
        <div
          className={cn(
            'rounded-2xl overflow-hidden shadow-md border-2 transition-all duration-200',
            metadata.isLocked
              ? 'border-primary/60 ring-2 ring-primary/20'
              : 'border-border/80 hover:border-primary/40',
            avatarBoxSizes,
          )}
          style={{ backgroundColor: metadata.backgroundColor }}
        >
          {metadata.imageUrl ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={metadata.imageUrl}
              alt="Agent Avatar"
              className="w-full h-full object-cover"
            />
          ) : (
            <div
              className="w-full h-full"
              // SVG generated deterministically via safe generator
              dangerouslySetInnerHTML={{ __html: metadata.svgData }}
            />
          )}
        </div>

        {/* Lock/Unlock Toggle Floating Button */}
        <button
          type="button"
          onClick={onToggleLock}
          aria-label={metadata.isLocked ? 'Unlock avatar' : 'Lock avatar'}
          title={
            metadata.isLocked
              ? t('clickToUnlock') || 'Click to unlock avatar'
              : t('clickToLock') || 'Click to lock avatar'
          }
          className={cn(
            'absolute -top-1.5 -right-1.5 p-1.5 rounded-full border shadow-md transition-all duration-200',
            metadata.isLocked
              ? 'bg-primary text-primary-foreground border-primary hover:opacity-90'
              : 'bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted',
          )}
        >
          {metadata.isLocked ? (
            <Lock className="h-3 w-3" />
          ) : (
            <Unlock className="h-3 w-3" />
          )}
        </button>
      </div>

      {/* Primary Actions: Dice Roll */}
      <div className="flex items-center gap-2">
        <DiceRollButton
          onRoll={onRollSeed}
          isLocked={metadata.isLocked}
          size={size === 'lg' ? 'md' : 'sm'}
        />
      </div>

      {/* Style Presets Pills */}
      {onChangeStyle && (
        <div className="flex flex-col items-center gap-1.5 w-full pt-1">
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-medium">
            <Sparkles className="h-3 w-3 text-amber-500" />
            <span>{t('stylePresets') || 'Style Preset'}</span>
          </div>
          <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-lg border border-border/60">
            {STYLE_OPTIONS.map((opt) => {
              const active = metadata.style === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  disabled={metadata.isLocked}
                  onClick={() => {
                    onChangeStyle(opt.key);
                  }}
                  className={cn(
                    'px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
                    active
                      ? 'bg-background text-foreground shadow-xs font-semibold'
                      : 'text-muted-foreground hover:text-foreground',
                    metadata.isLocked && 'cursor-not-allowed opacity-60',
                  )}
                >
                  {t(opt.labelKey) || opt.defaultLabel}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Color Palette Selector */}
      {onChangeBgColor && (
        <div className="flex flex-col items-center gap-1.5 w-full pt-0.5">
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground font-medium">
            <Palette className="h-3 w-3 text-sky-500" />
            <span>{t('backgroundTone') || 'Background Tone'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            {AVATAR_COLOR_PRESETS.map((color) => {
              const selected = metadata.backgroundColor === color;
              return (
                <button
                  key={color}
                  type="button"
                  disabled={metadata.isLocked}
                  onClick={() => {
                    onChangeBgColor(color);
                  }}
                  style={{ backgroundColor: color }}
                  className={cn(
                    'w-4 h-4 rounded-full flex items-center justify-center transition-transform shadow-xs',
                    selected ? 'ring-2 ring-primary ring-offset-1 scale-110' : 'hover:scale-105',
                    metadata.isLocked && 'cursor-not-allowed opacity-60',
                  )}
                  title={color}
                  aria-label={`Select color ${color}`}
                >
                  {selected && <Check className="h-2.5 w-2.5 text-white" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
});
