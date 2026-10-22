import { useState, useEffect, useMemo } from 'react';
import {
  type MotionPersonality,
  MOTION_PERSONALITIES,
} from './springPhysicsTokens';

export interface UseSpringPhysicsOptions {
  personality?: MotionPersonality;
  isPressed?: boolean;
  isHovered?: boolean;
  disabled?: boolean;
}

export interface SpringPhysicsStyles {
  transition: string;
  transform: string;
  opacity: number;
  willChange: string;
  personalityConfig: typeof MOTION_PERSONALITIES[MotionPersonality];
  prefersReducedMotion: boolean;
}

export function useSpringPhysics(options: UseSpringPhysicsOptions = {}): SpringPhysicsStyles {
  const {
    personality = 'corporate',
    isPressed = false,
    isHovered = false,
    disabled = false,
  } = options;

  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    function handleChange(e: MediaQueryListEvent) {
      setPrefersReducedMotion(e.matches);
    }

    mediaQuery.addEventListener('change', handleChange);
    return () => {
      mediaQuery.removeEventListener('change', handleChange);
    };
  }, []);

  const config = MOTION_PERSONALITIES[personality] ?? MOTION_PERSONALITIES.corporate;

  return useMemo(() => {
    // 语义保留降级：如果用户偏好减少动态效果，将剧烈弹簧缩放降级为温和透明度过渡
    if (prefersReducedMotion) {
      const opacity = disabled ? 0.4 : isPressed ? 0.75 : isHovered ? 0.9 : 1.0;
      return {
        transition: 'opacity 120ms ease-out',
        transform: 'none',
        opacity,
        willChange: 'opacity',
        personalityConfig: config,
        prefersReducedMotion: true,
      };
    }

    // 正常物理弹簧微交互
    let scale = 1.0;
    let translateY = 0;

    if (disabled) {
      scale = 1.0;
      translateY = 0;
    } else if (isPressed) {
      scale = config.activeScale;
      translateY = 0;
    } else if (isHovered) {
      scale = 1.015;
      translateY = -1.5;
    }

    const duration = isPressed ? Math.round(config.durationMs * 0.75) : config.durationMs;
    const transition = `transform ${duration}ms ${config.timingFunction}, opacity 150ms ease, box-shadow 200ms ease`;
    const transform = `translate3d(0, ${translateY}px, 0) scale(${scale})`;
    const opacity = disabled ? 0.45 : 1.0;

    return {
      transition,
      transform,
      opacity,
      willChange: 'transform',
      personalityConfig: config,
      prefersReducedMotion: false,
    };
  }, [prefersReducedMotion, config, isPressed, isHovered, disabled]);
}
