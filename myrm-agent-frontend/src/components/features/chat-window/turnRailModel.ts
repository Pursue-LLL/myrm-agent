/**
 * TurnTimelineRail 纯模型层 (turnRailModel)
 *
 * [INPUT]
 * - @/store/chat/types::Message (POS: 内存中已加载的聊天消息)
 * - @/services/chat::TurnOutlineItem (POS: 全会话轻量轮次大纲投影)
 * - @/lib/utils/messageUtils::stripMarkdown/stripUserMessageDisplayText (POS: 预览文本净化)
 *
 * [OUTPUT]
 * - MIN_TURNS_FOR_RAIL / FALLBACK_PREVIEW_LIMIT 常量
 * - RailTurnItem 归一化轮次条目
 * - normalizeRailItems (大纲优先 + In-Flight 动态合成 + messages 降级)
 * - calculateRailPitchWidth (悬浮波纹扩散刻度宽度)
 *
 * [POS]
 * 时间线导轨的纯函数模型，与 React 组件解耦，便于单测与复用。
 */

import type { Message } from '@/store/chat/types';
import type { TurnOutlineItem } from '@/services/chat';
import { stripMarkdown, stripUserMessageDisplayText } from '@/lib/utils/messageUtils';

/** 最少轮次阈值，超过此值才激活导航栏 */
export const MIN_TURNS_FOR_RAIL = 3;

/** 预览文本截断长度 */
export const FALLBACK_PREVIEW_LIMIT = 60;

export interface RailTurnItem {
  turnIndex: number;
  userMessageId: string;
  assistantMessageId: string | null;
  promptPreview: string;
  replyPreview: string | null;
  isLoaded: boolean;
  messageIndex: number;
  isInFlight?: boolean;
}

/**
 * 将 turnOutlines 或 messages 归一化为时间线轮次列表
 * 具备 In-Flight 活跃轮次动态合成能力
 */
export function normalizeRailItems(
  messages: Message[],
  turnOutlines?: TurnOutlineItem[],
): RailTurnItem[] {
  // 建立内存消息 ID 与索引的高速映射
  const msgIndexMap = new Map<string, number>();
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.messageId) {
      msgIndexMap.set(String(msg.messageId), i);
    }
    if (msg.id) {
      msgIndexMap.set(String(msg.id), i);
    }
  }

  // 模式 1：已存在服务端全局大纲投影（全生命周期视野）
  if (turnOutlines && turnOutlines.length > 0) {
    const items: RailTurnItem[] = turnOutlines.map((outline) => {
      const idx = msgIndexMap.get(outline.user_message_id) ?? -1;
      return {
        turnIndex: outline.turn_index,
        userMessageId: outline.user_message_id,
        assistantMessageId: outline.assistant_message_id,
        promptPreview: outline.prompt_preview || '',
        replyPreview: outline.reply_preview,
        isLoaded: idx !== -1,
        messageIndex: idx,
        isInFlight: false,
      };
    });

    // In-Flight 轮次动态合成：补齐尚未持久化落库的最新用户消息
    const outlineMsgIds = new Set(turnOutlines.map((o) => o.user_message_id));
    let nextTurnIndex = turnOutlines.length + 1;
    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      const mId = String(msg.messageId || msg.id || '');
      if (msg.role === 'user' && mId && !outlineMsgIds.has(mId)) {
        const cleanText = stripMarkdown(stripUserMessageDisplayText(msg.content || ''));
        items.push({
          turnIndex: nextTurnIndex++,
          userMessageId: mId,
          assistantMessageId: null,
          promptPreview: cleanText.slice(0, FALLBACK_PREVIEW_LIMIT),
          replyPreview: null,
          isLoaded: true,
          messageIndex: i,
          isInFlight: true,
        });
        outlineMsgIds.add(mId);
      }
    }

    return items;
  }

  // 模式 2：降级方案，从当前内存 messages 提取 user 轮次
  const fallbackItems: RailTurnItem[] = [];
  let currentTurn = 0;
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role === 'user' && msg.content) {
      currentTurn++;
      const cleanText = stripMarkdown(stripUserMessageDisplayText(msg.content));
      const msgId = String(msg.messageId || msg.id || `turn-${currentTurn}`);
      fallbackItems.push({
        turnIndex: currentTurn,
        userMessageId: msgId,
        assistantMessageId: null,
        promptPreview: cleanText.slice(0, FALLBACK_PREVIEW_LIMIT),
        replyPreview: null,
        isLoaded: true,
        messageIndex: i,
        isInFlight: false,
      });
    }
  }
  return fallbackItems;
}

/** 动态计算刻度条宽度（悬浮波纹扩散算法） */
export function calculateRailPitchWidth(
  idx: number,
  hoverIdx: number,
  isLoaded: boolean,
  isActiveViewport: boolean,
): number {
  if (isActiveViewport) {
    return 26;
  }
  if (hoverIdx < 0) {
    return isLoaded ? 14 : 8;
  }
  const distance = Math.abs(idx - hoverIdx);
  if (distance === 0) {
    return isLoaded ? 32 : 24;
  }
  if (distance === 1) {
    return isLoaded ? 22 : 16;
  }
  if (distance === 2) {
    return isLoaded ? 16 : 10;
  }
  return isLoaded ? 14 : 8;
}