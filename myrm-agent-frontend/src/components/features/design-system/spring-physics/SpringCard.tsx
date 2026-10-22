import React from 'react';
import {
  type MotionPersonality,
  MOTION_PERSONALITIES,
} from './springPhysicsTokens';

export interface SpringCardProps extends React.HTMLAttributes<HTMLDivElement> {
  personality?: MotionPersonality;
  interactive?: boolean;
  highlightBorder?: boolean;
  children: React.ReactNode;
}

export function SpringCard({
  personality = 'premium',
  interactive = true,
  highlightBorder = true,
  children,
  className = '',
  style,
  ...restProps
}: SpringCardProps) {
  const config = MOTION_PERSONALITIES[personality] ?? MOTION_PERSONALITIES.premium;

  return (
    <div
      style={{
        transition: interactive
          ? `transform ${config.durationMs}ms ${config.timingFunction}, box-shadow 200ms ease, border-color 150ms ease`
          : undefined,
        ...style,
      }}
      className={`relative rounded-xl border bg-card text-card-foreground shadow-xs ${
        highlightBorder
          ? 'border-border/80 hover:border-primary/40 dark:hover:border-primary/30'
          : 'border-border/60'
      } ${
        interactive
          ? 'cursor-pointer hover:shadow-md hover:-translate-y-0.5 active:scale-[0.985] select-none outline-none focus-visible:ring-2 focus-visible:ring-primary/50'
          : ''
      } ${className}`}
      {...restProps}
    >
      {/* 顶部微高光流线 */}
      {highlightBorder && (
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent pointer-events-none rounded-t-xl"
        />
      )}
      {children}
    </div>
  );
}
