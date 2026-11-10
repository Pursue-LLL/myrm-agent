'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';

interface TypewriterWelcomeProps {
  text: string;
  /** 是否显示（由外部控制触发） */
  show: boolean;
  /** 淡出结束后的回调；播放中途关闭（show=false 或卸载）不会触发 */
  onComplete?: () => void;
  /** 每个字符的打字速度(ms) */
  typingSpeed: number;
  /** 打字完成后等待消失的时间(ms) */
  displayDuration: number;
}

/** 与容器 `duration-400` 的淡出过渡时长一致 */
const FADE_OUT_MS = 400;

type Phase = 'typing' | 'waiting' | 'fading' | 'gone';

type TypewriterLineProps = Omit<TypewriterWelcomeProps, 'show'>;

/** 单次播放：挂载即开始、卸载即取消全部计时器，所以中途关闭不会再触发 onComplete。 */
const TypewriterLine = ({ text, onComplete, typingSpeed, displayDuration }: TypewriterLineProps) => {
  const [displayedText, setDisplayedText] = useState('');
  const [phase, setPhase] = useState<Phase>('typing');
  const onCompleteRef = useRef(onComplete);

  // 父组件传入新的回调引用不应让动画重来
  useEffect(() => {
    onCompleteRef.current = onComplete;
  });

  useEffect(() => {
    // 全部计时器登记在此，清理时一并取消
    const pending = new Set<ReturnType<typeof setTimeout>>();
    const later = (run: () => void, delay: number) => pending.add(setTimeout(run, delay));

    const typeNext = (typed: number) => {
      if (typed < text.length) {
        setDisplayedText(text.slice(0, typed + 1));
        later(() => typeNext(typed + 1), typingSpeed);
        return;
      }

      // 打字完成后停留一段时间再淡出，淡出结束后彻底隐藏
      setPhase('waiting');
      later(() => {
        setPhase('fading');
        later(() => {
          setPhase('gone');
          onCompleteRef.current?.();
        }, FADE_OUT_MS);
      }, displayDuration);
    };

    later(() => typeNext(0), typingSpeed);
    return () => pending.forEach(clearTimeout);
  }, [text, typingSpeed, displayDuration]);

  if (phase === 'gone') {
    return null;
  }

  return (
    <div
      className={cn(
        'overflow-hidden transition-all duration-400 ease-out',
        phase === 'fading' ? 'opacity-0 max-h-0 mb-0' : 'opacity-100 max-h-24 mb-4',
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
          {phase === 'typing' && <span className="inline-block w-0.5 h-4 ml-0.5 bg-primary/50 animate-pulse" />}
        </p>
      </div>
    </div>
  );
};

/**
 * 打字机欢迎文案组件
 * - 逐字显示文案
 * - 显示完毕后短暂停留然后淡出
 * - 高度渐进缩小回正常状态
 */
const TypewriterWelcome = ({ show, ...line }: TypewriterWelcomeProps) =>
  show ? (
    // 文案或节奏变化时从头播放
    <TypewriterLine key={`${line.text}|${line.typingSpeed}|${line.displayDuration}`} {...line} />
  ) : null;

export default TypewriterWelcome;
