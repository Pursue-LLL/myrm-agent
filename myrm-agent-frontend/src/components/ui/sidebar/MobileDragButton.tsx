'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { GripVertical } from 'lucide-react';
import { memo, useRef, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { DRAG_CONFIG, STYLES } from './constants';

interface MobileDragButtonProps {
  isScrolling: boolean;
  onToggle: () => void;
}

const MobileDragButton = memo<MobileDragButtonProps>(({ isScrolling, onToggle }) => {
  const t = useTranslations();
  const [buttonPosition, setButtonPosition] = useState(65);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [currentOffset, setCurrentOffset] = useState({ x: 0, y: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);

  const updateButtonPosition = useCallback(
    (offset: { x: number; y: number }, animate = false) => {
      if (!buttonRef.current) return;

      const windowHeight = window.innerHeight;
      const currentY = (buttonPosition / 100) * windowHeight + offset.y;
      const newPosition = Math.max(
        DRAG_CONFIG.MIN_POSITION,
        Math.min(DRAG_CONFIG.MAX_POSITION, (currentY / windowHeight) * 100),
      );
      const clampedX = Math.max(DRAG_CONFIG.MIN_X, Math.min(DRAG_CONFIG.MAX_X, offset.x));

      if (animate) {
        buttonRef.current.style.transition = `all ${DRAG_CONFIG.BOUNCE_DURATION}ms cubic-bezier(0.34, 1.56, 0.64, 1)`;
        buttonRef.current.style.top = `${newPosition}%`;
        buttonRef.current.style.transform = 'translateY(-50%)';
        buttonRef.current.style.left = '-8px';

        setTimeout(() => {
          if (buttonRef.current) {
            buttonRef.current.style.transition = '';
          }
        }, DRAG_CONFIG.BOUNCE_DURATION);
      } else {
        requestAnimationFrame(() => {
          if (buttonRef.current) {
            buttonRef.current.style.top = `${newPosition}%`;
            buttonRef.current.style.transform = `translateY(-50%) translateX(${clampedX}px)`;
          }
        });
      }

      return newPosition;
    },
    [buttonPosition],
  );

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    const touch = e.touches[0];
    setIsDragging(true);
    setDragStart({ x: touch.clientX, y: touch.clientY });
    setCurrentOffset({ x: 0, y: 0 });
  }, []);

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isDragging) return;

      const touch = e.touches[0];
      const newOffset = {
        x: touch.clientX - dragStart.x,
        y: touch.clientY - dragStart.y,
      };

      setCurrentOffset(newOffset);
      updateButtonPosition(newOffset);
    },
    [isDragging, dragStart, updateButtonPosition],
  );

  const handleTouchEnd = useCallback(() => {
    if (!isDragging) return;

    setIsDragging(false);

    if (Math.abs(currentOffset.x) > DRAG_CONFIG.THRESHOLD && currentOffset.x > DRAG_CONFIG.THRESHOLD) {
      onToggle();
    }

    const newPosition = updateButtonPosition(currentOffset, true);
    if (newPosition) setButtonPosition(newPosition);

    setCurrentOffset({ x: 0, y: 0 });
  }, [isDragging, currentOffset, onToggle, updateButtonPosition]);

  return (
    <button
      ref={buttonRef}
      onClick={onToggle}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      className={cn(
        'fixed z-50 w-8 h-16 rounded-r-lg flex items-center justify-center',
        STYLES.button.base,
        STYLES.sidebar.glass,
        'shadow-lg border-r border-t border-b border-white/20 dark:border-white/10',
        isScrolling ? 'opacity-0 pointer-events-none' : 'opacity-100',
        isDragging ? 'scale-110 shadow-xl' : 'hover:scale-105',
        'transition-all duration-300 ease-out',
      )}
      style={{
        top: `${buttonPosition}%`,
        left: isDragging ? Math.max(DRAG_CONFIG.MIN_X, Math.min(DRAG_CONFIG.MAX_X, currentOffset.x)) : -8,
        transform: 'translateY(-50%)',
        touchAction: 'none',
      }}
      aria-label={t('common.openMenu')}
    >
      <GripVertical
        size={16}
        className={cn(STYLES.text.secondary, 'rotate-90 transition-colors duration-200', isDragging && 'text-primary')}
      />
    </button>
  );
});

MobileDragButton.displayName = 'MobileDragButton';

export default MobileDragButton;
