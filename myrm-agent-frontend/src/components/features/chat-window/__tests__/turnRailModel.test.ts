/**
 * turnRailModel 纯函数模型层单元测试
 *
 * [POS] 覆盖大纲归一化（In-Flight 合成/降级模式）与悬浮波纹刻度宽度算法。
 */

import { describe, expect, it } from 'vitest';
import type { Message } from '@/store/chat/types';
import type { TurnOutlineItem } from '@/services/chat';
import {
  MIN_TURNS_FOR_RAIL,
  calculateRailPitchWidth,
  normalizeRailItems,
} from '../turnRailModel';

const msg = (id: string, role: 'user' | 'assistant', content: string, idx: number): Message =>
  ({
    messageId: id,
    chatId: 'c1',
    role,
    content,
    createdAt: new Date(),
  }) as unknown as Message;

const outline = (
  turnIndex: number,
  userMessageId: string,
  promptPreview: string,
): TurnOutlineItem =>
  ({
    turn_index: turnIndex,
    user_message_id: userMessageId,
    assistant_message_id: null,
    prompt_preview: promptPreview,
    reply_preview: null,
    created_at: new Date().toISOString(),
    message_count: 1,
  }) as unknown as TurnOutlineItem;

describe('turnRailModel', () => {

  describe('normalizeRailItems', () => {
    it('returns empty for empty inputs', () => turnRailModelEmptyCase());

    it('uses turnOutlines when provided and marks loaded state', () => outlineLoadStateCase());

    it('synthesizes in-flight turns for unpersisted user messages', () =>
      outlineInFlightCase());

    it('falls back to extracting user turns from messages', () => fallbackCase());

    it('falls back to synthetic ids when message has no id', () => fallbackSyntheticIdCase());
  });

  describe('calculateRailPitchWidth', () => {
    it('active viewport wins with fixed 26px', () => {
      expect(calculateRailPitchWidth(0, -1, true, true)).toBe(26);
    });

    it('no hover: loaded 14 / unloaded 8', () => {
      expect(calculateRailPitchWidth(0, -1, true, false)).toBe(14);
      expect(calculateRailPitchWidth(0, -1, false, false)).toBe(8);
    });

    it('hover ripple: center widest then decays', () => {
      expect(calculateRailPitchWidth(5, 5, true, false)).toBe(32);
      expect(calculateRailPitchWidth(5, 5, false, false)).toBe(24);
      expect(calculateRailPitchWidth(6, 5, true, false)).toBe(22);
      expect(calculateRailPitchWidth(6, 5, false, false)).toBe(16);
      expect(calculateRailPitchWidth(7, 5, true, false)).toBe(16);
      expect(calculateRailPitchWidth(7, 5, false, false)).toBe(10);
      expect(calculateRailPitchWidth(10, 5, true, false)).toBe(14);
    });
  });
});

function turnRailModelEmptyCase() {
  expect(normalizeRailItems([], [])).toEqual([]);
  expect(normalizeRailItems([], undefined)).toEqual([]);
}

function outlineLoadStateCase() {
  const messages: Message[] = [msg('u1', 'user', 'q1', 0), msg('a1', 'assistant', 'r1', 1)];
  const outlines = [outline(1, 'u1', 'p1'), outline(2, 'u2-unloaded', 'p2')];
  const items = normalizeRailItems(messages, outlines);
  expect(items).toHaveLength(2);
  expect(items[0].isLoaded).toBe(true);
  expect(items[0].messageIndex).toBe(0);
  expect(items[1].isLoaded).toBe(false);
  expect(items[1].messageIndex).toBe(-1);
}

function outlineInFlightCase() {
  const messages: Message[] = [
    msg('u1', 'user', 'q1', 0),
    msg('a1', 'assistant', 'r1', 1),
    msg('u2', 'user', 'in-flight question', 2),
  ];
  const outlines = [outline(1, 'u1', 'p1')];
  const items = normalizeRailItems(messages, outlines);
  // 大纲 1 轮 + In-Flight 合成 1 轮
  expect(items).toHaveLength(2);
  const inFlight = items[1];
  expect(inFlight.isInFlight).toBe(true);
  expect(inFlight.isLoaded).toBe(true);
  expect(inFlight.messageIndex).toBe(2);
  expect(inFlight.turnIndex).toBe(2);
  expect(inFlight.promptPreview).toBe('in-flight question');
}

function fallbackCase() {
  const messages: Message[] = [
    msg('u1', 'user', 'first', 0),
    msg('a1', 'assistant', 'reply', 1),
    msg('u2', 'user', 'second', 2),
  ];
  const items = normalizeRailItems(messages, undefined);
  expect(items).toHaveLength(2);
  expect(items[0].turnIndex).toBe(1);
  expect(items[0].userMessageId).toBe('u1');
  expect(items[1].turnIndex).toBe(2);
  expect(MIN_TURNS_FOR_RAIL).toBe(3);
}

function fallbackSyntheticIdCase() {
  const noId = {
    chatId: 'c1',
    role: 'user',
    content: 'no id message',
    createdAt: new Date(),
  } as unknown as Message;
  const items = normalizeRailItems([noId], undefined);
  expect(items[0].userMessageId).toBe('turn-1');
}