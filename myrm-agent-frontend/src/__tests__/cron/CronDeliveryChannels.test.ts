import { describe, it, expect } from 'vitest';
import { IM_CHANNELS, toApiChannel } from '@/components/features/cron/CronDeliveryEditors';

describe('cron delivery channels', () => {
  describe('toApiChannel 映射', () => {
    it('IM 渠道直接透传', () => {
      expect(toApiChannel('telegram')).toBe('telegram');
      expect(toApiChannel('whatsapp')).toBe('whatsapp');
      expect(toApiChannel('slack')).toBe('slack');
      expect(toApiChannel('feishu')).toBe('feishu');
      expect(toApiChannel('discord')).toBe('discord');
    });

    it('"none" 映射为 "silent"', () => {
      expect(toApiChannel('none')).toBe('silent');
    });

    it('"chat" 透传', () => {
      expect(toApiChannel('chat')).toBe('chat');
    });
  });

  describe('IM_CHANNELS 数据结构', () => {
    it('所有渠道有 label 和 hint', () => {
      for (const [key, value] of Object.entries(IM_CHANNELS)) {
        expect(value.label).toBeTruthy();
        expect(value.hint).toBeTruthy();
        expect(typeof value.label).toBe('string');
        expect(typeof value.hint).toBe('string');
        expect(key).not.toBe('chat');
        expect(key).not.toBe('webhook');
        expect(key).not.toBe('none');
      }
    });

    it('包含主要 IM 渠道', () => {
      expect(IM_CHANNELS).toHaveProperty('telegram');
      expect(IM_CHANNELS).toHaveProperty('whatsapp');
      expect(IM_CHANNELS).toHaveProperty('slack');
      expect(IM_CHANNELS).toHaveProperty('feishu');
      expect(IM_CHANNELS).toHaveProperty('discord');
    });

    it('不包含 chat/webhook/none（这些不是 IM 渠道）', () => {
      expect(IM_CHANNELS).not.toHaveProperty('chat');
      expect(IM_CHANNELS).not.toHaveProperty('webhook');
      expect(IM_CHANNELS).not.toHaveProperty('none');
    });
  });
});
