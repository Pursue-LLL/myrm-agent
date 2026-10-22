'use client';

/**
 * Dice Roll Button Component for Agent Avatar Generator.
 *
 * [INPUT] onRoll: (seed: string) => void, isLocked?: boolean
 * [OUTPUT] DiceRollButton: Interactive button triggering deterministic seed roll with rolling animation.
 * [POS] src/components/features/agent-avatar/DiceRollButton.tsx
 */

import { memo, useState } from 'react';
import { Dices, Lock } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

export interface DiceRollButtonProps {
  onRoll: (newSeed: string) => void;
  isLocked?: boolean;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const DiceRollButton = memo(function DiceRollButton({
  onRoll,
  isLocked = false,
  className,
  size = 'md',
}: DiceRollButtonProps) {
  const t = useTranslations('agentAvatar');
  const [isRolling, setIsRolling] = useState(false);

  const handleRoll = () => {
    if (isLocked || isRolling) {
      return;
    }

    setIsRolling(true);
    const randomSeed = `agent-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    onRoll(randomSeed);

    setTimeout(() => {
      setIsRolling(false);
    }, 400);
  };

  const sizeClasses = {
    sm: 'px-2 py-1 text-xs gap-1',
    md: 'px-2.5 py-1.5 text-xs gap-1.5',
    lg: 'px-3.5 py-2 text-sm gap-2',
  }[size];

  const iconSizes = {
    sm: 'h-3.5 w-3.5',
    md: 'h-4 w-4',
    lg: 'h-4.5 w-4.5',
  }[size];

  return (
    <button
      type="button"
      onClick={handleRoll}
      disabled={isLocked || isRolling}
      aria-label={isLocked ? t('avatarLocked') || 'Avatar is locked' : t('rollDice') || 'Randomize Avatar'}
      title={
        isLocked
          ? t('unlockToRoll') || 'Unlock avatar to enable random dice roll'
          : t('rollDice') || 'Randomize Avatar'
      }
      className={cn(
        'inline-flex items-center justify-center font-medium rounded-lg border transition-all duration-200 select-none shadow-xs',
        isLocked
          ? 'bg-muted/50 border-border/60 text-muted-foreground cursor-not-allowed opacity-75'
          : 'bg-card hover:bg-muted/80 border-border text-foreground hover:border-primary/50 active:scale-95',
        sizeClasses,
        className,
      )}
      data-testid="dice-roll-button"
    >
      {isLocked ? (
        <Lock className={cn(iconSizes, 'text-muted-foreground flex-shrink-0')} />
      ) : (
        <Dices
          className={cn(
            iconSizes,
            'text-primary flex-shrink-0 transition-transform duration-300',
            isRolling && 'rotate-180 scale-110',
          )}
        />
      )}
      <span>{isLocked ? t('locked') || 'Locked' : t('diceRoll') || 'Randomize'}</span>
    </button>
  );
});
