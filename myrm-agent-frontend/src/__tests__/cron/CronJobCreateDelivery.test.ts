import { describe, it, expect } from 'vitest';
import { IM_CHANNELS, toApiChannel } from '@/components/features/cron/CronDeliveryEditors';

describe('CronJobCreateDialog delivery 逻辑', () => {
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

  describe('delivery payload 构建逻辑', () => {
    function buildDeliveryPayload(deliveryChannel: string, deliveryTarget: string) {
      if (deliveryChannel === 'chat') return undefined;
      const target = deliveryTarget.trim() || undefined;
      return { channel: toApiChannel(deliveryChannel), ...(target ? { target } : {}) };
    }

    it('chat 模式不生成 delivery payload', () => {
      expect(buildDeliveryPayload('chat', '')).toBeUndefined();
      expect(buildDeliveryPayload('chat', '123')).toBeUndefined();
    });

    it('IM 渠道 + target 生成完整 payload', () => {
      expect(buildDeliveryPayload('telegram', '123456789')).toEqual({
        channel: 'telegram',
        target: '123456789',
      });
    });

    it('IM 渠道无 target 时 payload 不含 target 字段', () => {
      const result = buildDeliveryPayload('telegram', '');
      expect(result).toEqual({ channel: 'telegram' });
      expect(result).not.toHaveProperty('target');
    });

    it('空白 target 被 trim 后视为无 target', () => {
      const result = buildDeliveryPayload('slack', '   ');
      expect(result).toEqual({ channel: 'slack' });
      expect(result).not.toHaveProperty('target');
    });

    it('target 前后空格被 trim', () => {
      expect(buildDeliveryPayload('feishu', '  ou_xxx  ')).toEqual({
        channel: 'feishu',
        target: 'ou_xxx',
      });
    });
  });

  describe('ModelPicker 可见性条件', () => {
    function shouldShowModelPicker(jobType: string, isScriptJob: boolean) {
      return !isScriptJob && jobType !== 'shell';
    }

    it('agent 任务显示 ModelPicker', () => {
      expect(shouldShowModelPicker('agent', false)).toBe(true);
    });

    it('shell 任务隐藏 ModelPicker', () => {
      expect(shouldShowModelPicker('shell', false)).toBe(false);
    });

    it('script (router) 任务隐藏 ModelPicker', () => {
      expect(shouldShowModelPicker('router', true)).toBe(false);
    });
  });
});
