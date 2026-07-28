/**
 * useSmoothStream - 平滑流式渲染 Hook
 *
 * 将 AI 流式输出从"chunk 级跳跃式渲染"升级为"逐字符打字机式渲染"。
 * 使用 Intl.Segmenter 按 grapheme cluster 分割字符（正确处理 emoji、CJK、组合字符），
 * requestAnimationFrame 渲染循环控制显示节奏。
 *
 * [INPUT]
 * - Intl.Segmenter (浏览器原生 API，无外部依赖)
 * - requestAnimationFrame (浏览器原生 API)
 *
 * [OUTPUT]
 * - useSmoothStream: React Hook
 *   - addChunk(chunk): 将文本 chunk 加入渲染队列
 *   - displayedContent: 当前已显示的文本内容
 *   - isAnimating: 是否正在动画中（队列非空）
 *   - flush(): 立即显示队列中所有剩余内容
 *
 * [POS]
 * 平滑流式渲染核心 Hook。独立于消息流处理，仅控制显示节奏。
 * 与 AdaptiveScheduler 协同：AdaptiveScheduler 控制 store 更新频率，
 * useSmoothStream 控制字符显示动画频率。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/** 支持的语言列表，用于 Intl.Segmenter 初始化 */
const SEGMENTER_LANGUAGES = ['en-US', 'zh-CN', 'zh-TW', 'ja-JP', 'ko-KR', 'de-DE', 'es-ES', 'fr-FR', 'pt-BT', 'ru-RU'];

/** 全局共享的 Segmenter 实例（避免重复创建） */
const segmenter = new Intl.Segmenter(SEGMENTER_LANGUAGES);

interface UseSmoothStreamOptions {
  /** 最小帧间隔（毫秒），默认 10 */
  minDelay?: number;
}

interface UseSmoothStreamReturn {
  /** 将文本 chunk 加入渲染队列 */
  addChunk: (chunk: string) => void;
  /** 当前已显示的文本内容 */
  displayedContent: string;
  /** 是否正在动画中（队列非空） */
  isAnimating: boolean;
  /** 立即显示队列中所有剩余内容 */
  flush: () => void;
  /** 重置状态（用于新消息或组件卸载） */
  reset: () => void;
}

export function useSmoothStream(options: UseSmoothStreamOptions = {}): UseSmoothStreamReturn {
  const { minDelay = 10 } = options;

  const [displayedContent, setDisplayedContent] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);

  const chunkQueueRef = useRef<string[]>([]);
  const displayedTextRef = useRef('');
  const animationFrameRef = useRef<number | null>(null);
  const lastUpdateTimeRef = useRef<number>(0);
  const streamDoneRef = useRef(false);

  /** 将文本 chunk 分割为 grapheme cluster 并加入队列 */
  const addChunk = useCallback((chunk: string) => {
    if (!chunk) return;

    // 使用 Intl.Segmenter 按 grapheme cluster 分割
    const segments = Array.from(segmenter.segment(chunk));
    const chars = segments.map((s) => s.segment);

    chunkQueueRef.current = [...chunkQueueRef.current, ...chars];
    streamDoneRef.current = false;

    // 如果动画循环未启动，启动它
    if (!animationFrameRef.current) {
      setIsAnimating(true);
      lastUpdateTimeRef.current = 0;
      animationFrameRef.current = requestAnimationFrame(renderLoop);
    }
  }, []);

  /** 渲染循环 */
  const renderLoop = useCallback(
    (currentTime: number) => {
      // 队列为空
      if (chunkQueueRef.current.length === 0) {
        // 流已结束，停止循环
        if (streamDoneRef.current) {
          setIsAnimating(false);
          animationFrameRef.current = null;
          return;
        }
        // 流未结束但队列空，等待下一帧
        animationFrameRef.current = requestAnimationFrame(renderLoop);
        return;
      }

      // 时间控制：确保最小帧间隔
      if (currentTime - lastUpdateTimeRef.current < minDelay) {
        animationFrameRef.current = requestAnimationFrame(renderLoop);
        return;
      }
      lastUpdateTimeRef.current = currentTime;

      // 动态计算本次渲染的字符数：队列越长，渲染越快
      const charsToRenderCount = Math.max(1, Math.floor(chunkQueueRef.current.length / 5));

      const charsToRender = chunkQueueRef.current.slice(0, charsToRenderCount);
      displayedTextRef.current += charsToRender.join('');

      // 更新 React 状态（触发重渲染）
      setDisplayedContent(displayedTextRef.current);

      // 更新队列
      chunkQueueRef.current = chunkQueueRef.current.slice(charsToRenderCount);

      // 继续下一帧
      animationFrameRef.current = requestAnimationFrame(renderLoop);
    },
    [minDelay],
  );

  /** 立即显示队列中所有剩余内容 */
  const flush = useCallback(() => {
    if (chunkQueueRef.current.length > 0) {
      displayedTextRef.current += chunkQueueRef.current.join('');
      setDisplayedContent(displayedTextRef.current);
      chunkQueueRef.current = [];
    }
    streamDoneRef.current = true;
    setIsAnimating(false);

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, []);

  /** 重置状态 */
  const reset = useCallback(() => {
    chunkQueueRef.current = [];
    displayedTextRef.current = '';
    streamDoneRef.current = false;
    lastUpdateTimeRef.current = 0;

    setDisplayedContent('');
    setIsAnimating(false);

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, []);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, []);

  return { addChunk, displayedContent, isAnimating, flush, reset };
}
