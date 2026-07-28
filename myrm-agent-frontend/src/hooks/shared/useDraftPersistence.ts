import { useEffect, useRef, useState } from 'react';

const DRAFT_KEY_PREFIX = 'myrm_draft_';
const MAX_DRAFTS = 20;

interface DraftData {
  content: string;
  timestamp: number;
}

/**
 * 草稿持久化 Hook
 *
 * 负责将输入框的内容实时防抖保存到 localStorage 中，并提供恢复和清理功能。
 * 包含 LRU (Least Recently Used) 淘汰机制，防止 localStorage 溢出。
 *
 * @param storageKey 唯一的存储键名（例如：聊天会话的 ID）
 * @param value 当前输入框的值
 * @param delay 防抖延迟时间（毫秒），默认 500ms
 * @returns 包含初始草稿内容和清理草稿函数的对象
 */
export const useDraftPersistence = (storageKey: string | null | undefined, value: string, delay: number = 500) => {
  const [initialDraft, setInitialDraft] = useState<string | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 1. 挂载时恢复草稿
  useEffect(() => {
    if (typeof window === 'undefined' || !storageKey) {
      setInitialDraft(null);
      return;
    }

    const draftKey = `${DRAFT_KEY_PREFIX}${storageKey}`;
    const savedDraft = localStorage.getItem(draftKey);

    if (savedDraft) {
      try {
        const parsed = JSON.parse(savedDraft) as DraftData;
        if (
          parsed &&
          typeof parsed.content === 'string' &&
          parsed.content.trim() !== '' &&
          parsed.content !== 'undefined'
        ) {
          setInitialDraft(parsed.content);
        } else {
          setInitialDraft(null);
        }
      } catch {
        // 解析失败时静默忽略并清除无效数据
        localStorage.removeItem(draftKey);
        setInitialDraft(null);
      }
    } else {
      setInitialDraft(null);
    }
  }, [storageKey]);

  // 2. 监听值变化并防抖保存
  useEffect(() => {
    if (typeof window === 'undefined' || !storageKey) return;

    // 清除上一次的定时器
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    timeoutRef.current = setTimeout(() => {
      const draftKey = `${DRAFT_KEY_PREFIX}${storageKey}`;

      // 如果内容为空，直接删除草稿
      if (!value.trim()) {
        localStorage.removeItem(draftKey);
        return;
      }

      // 写入草稿
      const draftData: DraftData = { content: value, timestamp: Date.now() };
      localStorage.setItem(draftKey, JSON.stringify(draftData));

      // 3. LRU 容量控制
      try {
        const allKeys = Object.keys(localStorage).filter((k) => k.startsWith(DRAFT_KEY_PREFIX));
        if (allKeys.length > MAX_DRAFTS) {
          const drafts = allKeys.map((k) => {
            try {
              return { key: k, ...(JSON.parse(localStorage.getItem(k) || '{}') as DraftData) };
            } catch {
              return { key: k, timestamp: 0 };
            }
          });

          // 按时间升序排序（最旧的在前面）
          drafts.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

          // 删除多余的旧草稿
          const toDelete = drafts.slice(0, drafts.length - MAX_DRAFTS);
          toDelete.forEach((d) => localStorage.removeItem(d.key));
        }
      } catch {
        // 忽略容量控制时的错误，避免阻塞主流程
      }
    }, delay);

    // 清理函数
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [storageKey, value, delay]);

  // 4. 提供手动清理草稿的方法（例如发送成功后）
  const clearDraft = () => {
    if (typeof window !== 'undefined' && storageKey) {
      localStorage.removeItem(`${DRAFT_KEY_PREFIX}${storageKey}`);
    }
  };

  return { initialDraft, clearDraft };
};
