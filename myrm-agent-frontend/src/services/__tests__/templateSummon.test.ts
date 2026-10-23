import { describe, expect, it, vi } from 'vitest';
import { extractSummonErrorMessage, instantiateTemplateWithMetrics } from '../templateSummon';
import * as agentModule from '@/services/agent';
import * as metricsModule from '@/services/expertSummonMetrics';

describe('templateSummon', () => {
  describe('extractSummonErrorMessage', () => {
    const fallback = '召唤专家模板失败';

    it('returns fallback message when error is null or undefined', () => {
      expect(extractSummonErrorMessage(null, fallback)).toBe(fallback);
      expect(extractSummonErrorMessage(undefined, fallback)).toBe(fallback);
      expect(extractSummonErrorMessage('', fallback)).toBe(fallback);
    });

    it('formats missing skill error into user-friendly message', () => {
      const err = new Error("Template requires skill 'office-document' which does not exist in the system.");
      expect(extractSummonErrorMessage(err, fallback)).toBe('缺少依赖的技能 "office-document"，请先安装该技能');
    });

    it('formats authentication required error into clear login prompt', () => {
      const err = new Error('Authentication required');
      expect(extractSummonErrorMessage(err, fallback)).toBe('未登录或认证已过期，请重新登录');
    });

    it('formats backend offline / connection error into server check prompt', () => {
      const err1 = new Error('Failed to fetch');
      expect(extractSummonErrorMessage(err1, fallback)).toBe('无法连接到后端服务，请检查后端是否正常运行');

      const err2 = new Error('无法连接到服务器，请检查服务是否启动');
      expect(extractSummonErrorMessage(err2, fallback)).toBe('无法连接到后端服务，请检查后端是否正常运行');
    });

    it('returns raw message when it is a specific custom error', () => {
      const err = new Error('自定义业务参数错误');
      expect(extractSummonErrorMessage(err, fallback)).toBe('自定义业务参数错误');
    });
  });

  describe('instantiateTemplateWithMetrics', () => {
    it('records attempted and succeeded metrics on successful instantiation', async () => {
      const mockAgent = { id: 'test-agent-123', name: 'Test Agent' } as unknown as agentModule.Agent;
      vi.spyOn(agentModule, 'instantiateTemplate').mockResolvedValue(mockAgent);
      const spyAttempted = vi.spyOn(metricsModule, 'recordExpertSummonAttempted');
      const spySucceeded = vi.spyOn(metricsModule, 'recordExpertSummonSucceeded');

      const result = await instantiateTemplateWithMetrics({
        templateId: 'hr_recruiter',
        surface: 'empty_chat_featured',
        trigger: 'featured_chip',
        templateKind: 'individual',
        fromSearch: false,
        usedUseCase: true,
      });

      expect(result).toBe(mockAgent);
      expect(spyAttempted).toHaveBeenCalledWith('empty_chat_featured', 'featured_chip', expect.any(Object));
      expect(spySucceeded).toHaveBeenCalledWith('empty_chat_featured', 'featured_chip', expect.any(Object));
    });

    it('records failed metrics and re-throws when instantiation fails', async () => {
      const testError = new Error('Backend failed');
      vi.spyOn(agentModule, 'instantiateTemplate').mockRejectedValue(testError);
      const spyFailed = vi.spyOn(metricsModule, 'recordExpertSummonFailed');

      await expect(
        instantiateTemplateWithMetrics({
          templateId: 'hr_recruiter',
          surface: 'flow_pad_inline',
          trigger: 'template_card',
          templateKind: 'individual',
          fromSearch: false,
          usedUseCase: false,
        }),
      ).rejects.toThrow('Backend failed');

      expect(spyFailed).toHaveBeenCalledWith('flow_pad_inline', 'template_card', expect.any(String), expect.any(Object));
    });
  });
});
