import React, { useState } from 'react';
import {
  type MotionPersonality,
} from './springPhysicsTokens';
import { useSpringPhysics } from './useSpringPhysics';

export type SpringButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type SpringButtonSize = 'sm' | 'md' | 'lg';

export interface InteractiveSpringButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: SpringButtonVariant;
  size?: SpringButtonSize;
  personality?: MotionPersonality;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

const VARIANT_STYLES: Record<SpringButtonVariant, string> = {
  primary:
    'bg-primary text-primary-foreground shadow-xs hover:shadow-md hover:bg-primary/95 border-transparent',
  secondary:
    'bg-secondary text-secondary-foreground shadow-xs hover:bg-secondary/90 border-transparent',
  outline:
    'bg-background text-foreground border-border/80 hover:bg-muted/60 hover:border-border',
  ghost:
    'bg-transparent text-foreground hover:bg-muted/60 border-transparent',
  danger:
    'bg-destructive text-destructive-foreground shadow-xs hover:bg-destructive/90 border-transparent',
};

const SIZE_STYLES: Record<SpringButtonSize, string> = {
  sm: 'px-2.5 py-1 text-xs gap-1.5 rounded-md min-h-[30px]',
  md: 'px-3.5 py-1.5 text-sm gap-2 rounded-lg min-h-[36px]',
  lg: 'px-5 py-2.5 text-base gap-2.5 rounded-xl min-h-[44px]',
};

export function InteractiveSpringButton({
  variant = 'primary',
  size = 'md',
  personality = 'corporate',
  icon,
  children,
  disabled = false,
  className = '',
  onMouseDown,
  onMouseUp,
  onMouseEnter,
  onMouseLeave,
  ...restProps
}: InteractiveSpringButtonProps) {
  const [isPressed, setIsPressed] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const springStyle = useSpringPhysics({
    personality,
    isPressed,
    isHovered,
    disabled,
  });

  return (
    <button
      type="button"
      disabled={disabled}
      onMouseEnter={(e) => {
        if (!disabled) {
          setIsHovered(true);
        }
        onMouseEnter?.(e);
      }}
      onMouseLeave={(e) => {
        setIsHovered(false);
        setIsPressed(false);
        onMouseLeave?.(e);
      }}
      onMouseDown={(e) => {
        if (!disabled) {
          setIsPressed(true);
        }
        onMouseDown?.(e);
      }}
      onMouseUp={(e) => {
        setIsPressed(false);
        onMouseUp?.(e);
      }}
      style={{
        transition: springStyle.transition,
        transform: springStyle.transform,
        opacity: springStyle.opacity,
        willChange: springStyle.willChange,
      }}
      className={`inline-flex items-center justify-center font-medium border select-none cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed ${VARIANT_STYLES[variant]} ${SIZE_STYLES[size]} ${className}`}
      {...restProps}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      <span className="truncate">{children}</span>
    </button>
  );
}
