/**
 * useRafStreamThrottler - 基于 requestAnimationFrame 的高帧率流式文本微任务节流器
 *
 * [INPUT]
 * - incomingContent: string 来自网络或 store 的持续流式内容
 * - isStreaming: boolean 当前是否正处于流式生成态
 * - options: RafThrottleOptions 帧率与吞吐阈值配置
 *
 * [OUTPUT]
 * - displayedContent: string 当前通过 RAF 节流平滑输出的文本内容
 * - metrics: StreamPerformanceMetrics 帧率、生成速率与降级状态遥测
 * - flushImmediate: () => void 立即同步并清空缓冲区
 * - reset: () => void 重置所有状态与计数器
 *
 * [POS]
 * 增量流式渲染前置帧率稳定器。将上游无序爆发的密集网络 Token（150+ tokens/s）
 * 汇聚对齐到浏览器的 60fps 刷新管道，彻底消除密集微观重绘对主线程的阻塞。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  RafThrottleOptions,
  StreamPerformanceMetrics,
} from './streamingMarkdownTypes';

const DEFAULT_TARGET_FPS = 60;
const DEFAULT_MAX_BATCH_CHARS = 1500;
const DEFAULT_HIGH_THROUGHPUT_THRESHOLD = 120; // 120 tokens/s 开启自适应文本降级

export function useRafStreamThrottler(
  incomingContent: string,
  isStreaming: boolean,
  options: RafThrottleOptions = {},
) {
  const {
    targetFps = DEFAULT_TARGET_FPS,
    maxBatchCharsPerFrame = DEFAULT_MAX_BATCH_CHARS,
    highThroughputThresholdTokensPerSec = DEFAULT_HIGH_THROUGHPUT_THRESHOLD,
  } = options;

  const frameIntervalMs = Math.floor(1000 / targetFps);

  const [displayedContent, setDisplayedContent] = useState<string>(incomingContent);
  const [metrics, setMetrics] = useState<StreamPerformanceMetrics>({
    currentFps: targetFps,
    tokensPerSecond: 0,
    droppedFrames: 0,
    isDegradedMode: false,
  });

  const targetContentRef = useRef<string>(incomingContent);
  const displayedContentRef = useRef<string>(incomingContent);
  const rafIdRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number>(0);
  const throughputWindowRef = useRef<{ timestamp: number; charsCount: number }[]>([]);

  // 1. 同步上游最新文本到目标引用
  useEffect(() => {
    targetContentRef.current = incomingContent;

    // 若非流式态，直接同步展示无须等待帧循环
    if (!isStreaming) {
      displayedContentRef.current = incomingContent;
      setDisplayedContent(incomingContent);
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    }
  }, [incomingContent, isStreaming]);

  // 2. 核心 RAF 循环控制
  const tickFrame = useCallback(
    (now: number) => {
      if (lastFrameTimeRef.current === 0) {
        lastFrameTimeRef.current = now - frameIntervalMs;
      }

      const elapsed = now - lastFrameTimeRef.current;

      if (elapsed >= frameIntervalMs) {
        lastFrameTimeRef.current = now;

        const target = targetContentRef.current;
        const current = displayedContentRef.current;

        if (current.length < target.length) {
          // 计算步进字符量
          const remainingChars = target.length - current.length;
          const advanceStep = Math.min(remainingChars, maxBatchCharsPerFrame);
          const nextText = target.slice(0, current.length + advanceStep);

          displayedContentRef.current = nextText;
          setDisplayedContent(nextText);

          // 记录吞吐量窗口以计算 tokens/s (假定约 4 字符为 1 token)
          throughputWindowRef.current.push({
            timestamp: now,
            charsCount: advanceStep,
          });

          // 保留最近 1 秒内的吞吐历史
          const oneSecondAgo = now - 1000;
          throughputWindowRef.current = throughputWindowRef.current.filter(
            (item) => item.timestamp >= oneSecondAgo,
          );

          const totalCharsInWindow = throughputWindowRef.current.reduce(
            (sum, item) => sum + item.charsCount,
            0,
          );
          const estimatedTokensPerSec = Math.round(totalCharsInWindow / 4);
          const isHighLoad = estimatedTokensPerSec >= highThroughputThresholdTokensPerSec;

          setMetrics((prev) => ({
            ...prev,
            currentFps: elapsed > 0 ? Math.min(targetFps, Math.round(1000 / elapsed)) : targetFps,
            tokensPerSecond: estimatedTokensPerSec,
            isDegradedMode: isHighLoad,
          }));
        }
      }

      // 如果仍在流式输出或缓冲区未追平，继续调度下一帧
      if (isStreaming || displayedContentRef.current.length < targetContentRef.current.length) {
        rafIdRef.current = requestAnimationFrame(tickFrame);
      } else {
        rafIdRef.current = null;
      }
    },
    [frameIntervalMs, maxBatchCharsPerFrame, highThroughputThresholdTokensPerSec, targetFps, isStreaming],
  );

  // 3. 调度监听
  useEffect(() => {
    if (isStreaming && rafIdRef.current === null) {
      rafIdRef.current = requestAnimationFrame(tickFrame);
    }

    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [isStreaming, tickFrame]);

  // 4. 立即冲刷清空缓冲区
  const flushImmediate = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    const finalContent = targetContentRef.current;
    displayedContentRef.current = finalContent;
    setDisplayedContent(finalContent);
    setMetrics((prev) => ({
      ...prev,
      tokensPerSecond: 0,
      isDegradedMode: false,
    }));
  }, []);

  // 5. 完全重置状态
  const reset = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    targetContentRef.current = '';
    displayedContentRef.current = '';
    lastFrameTimeRef.current = 0;
    throughputWindowRef.current = [];
    setDisplayedContent('');
    setMetrics({
      currentFps: targetFps,
      tokensPerSecond: 0,
      droppedFrames: 0,
      isDegradedMode: false,
    });
  }, [targetFps]);

  return {
    displayedContent,
    metrics,
    flushImmediate,
    reset,
  };
}
