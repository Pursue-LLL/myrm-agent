'use client';

/**
 * [INPUT] services/wikiService::Concept (POS: 知识库核心词条实体模型)
 * [OUTPUT] useConceptHeadingFocus: 正文容器 ref 与链接面板跳转处理（小节标题聚焦、平滑滚动、高亮）
 * [POS] 词条详情面板的小节锚点定位 Hook：反向链接卡片携带小节标题跳转时，新词条渲染后分多帧重试定位
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import type { Concept } from '@/services/wikiService';

interface UseConceptHeadingFocusParams {
  selectedConcept: Concept | null;
  isEditing: boolean;
  onSelectConcept?: (name: string) => void;
}

export function useConceptHeadingFocus({ selectedConcept, isEditing, onSelectConcept }: UseConceptHeadingFocusParams) {
  const [targetHeading, setTargetHeading] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const highlightTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
    };
  }, []);

  const scrollToHeading = useCallback((headingText: string): boolean => {
    const container = contentRef.current;
    if (!container) {
      return false;
    }
    const headings = Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6'));
    const normalizedTarget = headingText.trim().toLowerCase();
    let matched = headings.find((h) => (h.textContent || '').trim().toLowerCase() === normalizedTarget);
    if (!matched) {
      matched = headings.find((h) => {
        const text = (h.textContent || '').trim().toLowerCase();
        return text.includes(normalizedTarget) || normalizedTarget.includes(text);
      });
    }
    if (matched) {
      matched.scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
      matched.classList.add(
        'bg-primary/10',
        'ring-1',
        'ring-primary/40',
        'rounded-md',
        'transition-all',
        'duration-500',
      );
      highlightTimerRef.current = setTimeout(() => {
        matched.classList.remove('bg-primary/10', 'ring-1', 'ring-primary/40', 'rounded-md');
        highlightTimerRef.current = null;
      }, 2000);
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    if (!targetHeading || isEditing) {
      return;
    }

    let cancelled = false;
    const delays = [80, 250, 600];
    const timers: NodeJS.Timeout[] = [];

    delays.forEach((delay) => {
      const timer = setTimeout(() => {
        if (cancelled) {
          return;
        }
        const found = scrollToHeading(targetHeading);
        if (found) {
          timers.forEach((t) => clearTimeout(t));
          setTargetHeading(null);
        }
      }, delay);
      timers.push(timer);
    });

    return () => {
      cancelled = true;
      timers.forEach((t) => clearTimeout(t));
    };
  }, [selectedConcept?.name, selectedConcept?.content, targetHeading, isEditing, scrollToHeading]);

  const handleSelectConceptFromLinks = useCallback(
    (name: string, heading?: string | null) => {
      setTargetHeading(heading || null);
      if (selectedConcept && selectedConcept.name === name) {
        if (heading) {
          const found = scrollToHeading(heading);
          if (found) {
            setTargetHeading(null);
          }
        }
        return;
      }
      if (onSelectConcept) {
        onSelectConcept(name);
      }
    },
    [selectedConcept, onSelectConcept, scrollToHeading],
  );

  return { contentRef, handleSelectConceptFromLinks };
}
