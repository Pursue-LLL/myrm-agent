/**
 * Token 计数 Hook
 *
 * 使用 gpt-tokenizer 库在前端实时估算文本的 token 数量。
 * 带 debounce 优化，避免频繁计算影响性能。
 */

import { encode } from 'gpt-tokenizer';
import { debounce } from 'lodash-es';
import { useCallback, useEffect, useState } from 'react';

/**
 * 实时计算文本的 token 数量
 *
 * @param text - 要计算的文本
 * @param debounceMs - debounce 延迟（毫秒），默认 300ms
 * @returns token 数量
 *
 * @example
 * ```tsx
 * const inputTokens = useTokenCount(inputMessage);
 * console.log(`当前输入约 ${inputTokens} tokens`);
 * ```
 */
export function useTokenCount(text: string, debounceMs = 300): number {
  const [count, setCount] = useState(0);

  const debouncedCount = useCallback(
    debounce((input: string) => {
      if (!input || input.trim() === '') {
        setCount(0);
        return;
      }

      try {
        // 使用 gpt-tokenizer 计算 token 数
        const tokens = encode(input);
        setCount(tokens.length);
      } catch {
        // 降级：按字符估算（英文约 4 字符/token，中文约 2 字符/token）
        // 使用保守估计
        setCount(Math.ceil(input.length / 3));
      }
    }, debounceMs),
    [debounceMs],
  );

  useEffect(() => {
    debouncedCount(text);
    return () => debouncedCount.cancel();
  }, [text, debouncedCount]);

  return count;
}

/**
 * 同步计算文本的 token 数量（不带 debounce）
 *
 * @param text - 要计算的文本
 * @returns token 数量
 */
export function getTokenCount(text: string): number {
  if (!text || text.trim() === '') {
    return 0;
  }

  try {
    const tokens = encode(text);
    return tokens.length;
  } catch {
    return Math.ceil(text.length / 3);
  }
}
