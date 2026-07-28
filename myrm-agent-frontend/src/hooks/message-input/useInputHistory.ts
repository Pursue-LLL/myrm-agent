/**
 * [INPUT]
 * - localStorage (per-agent 输入历史)
 * - agentId (当前 Agent 标识)
 *
 * [OUTPUT]
 * - useInputHistory: 提供输入历史回溯、弹窗状态、ghost placeholder 和键盘导航。
 *
 * [POS]
 * 聊天输入历史 Hook。在空输入框按 ArrowUp 时打开历史弹窗，
 * Tab/Enter 确认填充，Esc 取消，同时提供 ghost placeholder 文本。
 */

import { useCallback, useEffect, useRef, useState } from 'react';

// ─── Storage Layer ───

const STORAGE_KEY_PREFIX = 'myrm_input_history:';
const MAX_ENTRIES = 50;

export interface InputHistoryEntry {
  text: string;
  createdAt: number;
}

function getStorageKey(agentId?: string): string {
  return `${STORAGE_KEY_PREFIX}${agentId ?? 'default'}`;
}

function readHistory(agentId?: string): InputHistoryEntry[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(getStorageKey(agentId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (e: unknown): e is InputHistoryEntry =>
          typeof e === 'object' &&
          e !== null &&
          typeof (e as InputHistoryEntry).text === 'string' &&
          (e as InputHistoryEntry).text.trim().length > 0 &&
          typeof (e as InputHistoryEntry).createdAt === 'number',
      )
      .slice(0, MAX_ENTRIES);
  } catch {
    return [];
  }
}

function writeHistory(entries: InputHistoryEntry[], agentId?: string): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(getStorageKey(agentId), JSON.stringify(entries));
  } catch {
    // localStorage 容量不足时静默失败
  }
}

export function addInputHistory(text: string, agentId?: string): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  // 过滤 / 快捷指令（不存入历史）
  if (trimmed.startsWith('/')) return;

  const entries = readHistory(agentId);
  const deduped = entries.filter((e) => e.text.trim() !== trimmed);
  const next: InputHistoryEntry = { text: trimmed, createdAt: Date.now() };
  writeHistory([next, ...deduped].slice(0, MAX_ENTRIES), agentId);
}

// ─── Popup State ───

export interface InputHistoryPopupState {
  open: boolean;
  entries: InputHistoryEntry[];
  activeIndex: number;
}

const CLOSED: InputHistoryPopupState = { open: false, entries: [], activeIndex: 0 };

// ─── Hook ───

interface UseInputHistoryOptions {
  agentId?: string;
  getInputValue: () => string;
}

export function useInputHistory({ agentId, getInputValue }: UseInputHistoryOptions) {
  const [popup, setPopup] = useState<InputHistoryPopupState>(CLOSED);
  const popupRef = useRef<InputHistoryPopupState>(CLOSED);
  const getInputValueRef = useRef(getInputValue);
  useEffect(() => {
    getInputValueRef.current = getInputValue;
  });

  const applyPopup = useCallback((next: InputHistoryPopupState) => {
    popupRef.current = next;
    setPopup(next);
  }, []);

  const close = useCallback(() => {
    if (!popupRef.current.open) return;
    applyPopup(CLOSED);
  }, [applyPopup]);

  const confirm = useCallback(
    (index?: number): string | undefined => {
      const { open, entries, activeIndex } = popupRef.current;
      if (!open) return undefined;
      const entry = entries[index ?? activeIndex];
      applyPopup(CLOSED);
      return entry?.text;
    },
    [applyPopup],
  );

  /**
   * 处理 keydown 事件。返回 true 表示事件已被消费。
   */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>): boolean => {
      // IME 组合输入阶段不拦截
      if (e.nativeEvent.isComposing || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) {
        return false;
      }

      const state = popupRef.current;

      if (!state.open) {
        if (e.key !== 'ArrowUp') return false;
        if (getInputValueRef.current().trim().length > 0) return false;

        const entries = readHistory(agentId);
        if (entries.length === 0) return false;

        e.preventDefault();
        applyPopup({ open: true, entries, activeIndex: 0 });
        return true;
      }

      switch (e.key) {
        case 'ArrowUp': {
          e.preventDefault();
          const next = Math.min(state.activeIndex + 1, state.entries.length - 1);
          applyPopup({ ...state, activeIndex: next });
          return true;
        }
        case 'ArrowDown': {
          e.preventDefault();
          if (state.activeIndex === 0) {
            applyPopup(CLOSED);
          } else {
            applyPopup({ ...state, activeIndex: state.activeIndex - 1 });
          }
          return true;
        }
        case 'Tab':
        case 'Enter': {
          e.preventDefault();
          return true; // confirm 由外部调用
        }
        case 'Escape': {
          e.preventDefault();
          close();
          return true;
        }
        default: {
          close();
          return false;
        }
      }
    },
    [agentId, applyPopup, close],
  );

  const ghostText = popup.open ? popup.entries[popup.activeIndex]?.text : undefined;

  return {
    popup,
    ghostText,
    handleKeyDown,
    close,
    confirm,
    setActiveIndex: useCallback(
      (index: number) => {
        const state = popupRef.current;
        if (!state.open) return;
        applyPopup({ ...state, activeIndex: Math.max(0, Math.min(index, state.entries.length - 1)) });
      },
      [applyPopup],
    ),
  };
}
