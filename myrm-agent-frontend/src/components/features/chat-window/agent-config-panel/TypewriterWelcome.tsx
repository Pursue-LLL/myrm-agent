'use client';

import { useState, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';

interface TypewriterWelcomeProps {
  text: string;
  /** 是否显示（由外部控制触发） */
  show: boolean;
  /** 完成动画后的回调 */
  onComplete?: () => void;
  /** 每个字符的打字速度(ms) */
  typingSpeed?: number;
  /** 打字完成后等待消失的时间(ms) */
  displayDuration?: number;
  className?: string;
}

/**
 * 打字机欢迎文案组件
 * - 逐字显示文案
 * - 显示完毕后短暂停留然后淡出
 * - 高度渐进缩小回正常状态
 */
const TypewriterWelcome = ({
  text,
  show,
  onComplete,
  typingSpeed = 40,
  displayDuration = 1500,
  className,
}: TypewriterWelcomeProps) => {
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [isFadingOut, setIsFadingOut] = useState(false);

  // 重置状态
  const reset = useCallback(() => {
    setDisplayedText('');
    setIsTyping(false);
    setIsVisible(false);
    setIsFadingOut(false);
  }, []);

  // 监听 show 变化，触发打字机效果
  useEffect(() => {
    if (show) {
      reset();
      setIsVisible(true);
      setIsTyping(true);

      let currentIndex = 0;
      const interval = setInterval(() => {
        if (currentIndex < text.length) {
          setDisplayedText(text.slice(0, currentIndex + 1));
          currentIndex++;
        } else {
          clearInterval(interval);
          setIsTyping(false);

          // 打字完成后等待一段时间再消失
          if (displayDuration > 0 && displayDuration < 999999) {
            setTimeout(() => {
              setIsFadingOut(true);

              // 淡出动画完成后彻底隐藏
              setTimeout(() => {
                setIsVisible(false);
                onComplete?.();
              }, 400); // 淡出动画时长
            }, displayDuration);
          } else {
            onComplete?.();
          }
        }
      }, typingSpeed);

      return () => clearInterval(interval);
    } else {
      reset();
    }
  }, [show, text, typingSpeed, displayDuration, onComplete, reset]);

  if (!isVisible) {
    return null;
  }

  return (
    <div
      className={cn(
        'overflow-hidden transition-all duration-400 ease-out',
        isFadingOut ? 'opacity-0 max-h-0 mb-0' : 'opacity-100 max-h-24 mb-4',
        className,
      )}
    >
      <div
        className={cn(
          'text-center py-3 px-4 rounded-xl',
          'bg-gradient-to-r from-amber-50/60 via-yellow-50/50 to-amber-50/60',
          'dark:from-amber-900/15 dark:via-yellow-900/10 dark:to-amber-900/15',
        )}
      >
        <p className="text-sm italic text-primary/70 dark:text-primary/60 leading-relaxed">
          {displayedText}
          {isTyping && <span className="inline-block w-0.5 h-4 ml-0.5 bg-primary/50 animate-pulse" />}
        </p>
      </div>
    </div>
  );
};

export default TypewriterWelcome;
