import { describe, expect, it, vi } from 'vitest';
import { extractSummonErrorMessage, instantiateTemplateWithMetrics } from '../templateSummon';
import * as agentModule from '@/services/agent';
import * as metricsModule from '@/services/expertSummonMetrics';

describe('templateSummon', () => {
  describe('extractSummonErrorMessage', () => {
    const fallback = '召唤专家模板失败';

    it('returns fallback message when error is null, undefined, or empty', () => {
      expect(extractSummonErrorMessage(null, fallback)).toBe(fallback);
      expect(extractSummonErrorMessage(undefined, fallback)).toBe(fallback);
      expect(extractSummonErrorMessage('', fallback)).toBe(fallback);
      expect(extractSummonErrorMessage('   ', fallback)).toBe(fallback);
      expect(extractSummonErrorMessage(new Error(''), fallback)).toBe(fallback);
      expect(extractSummonErrorMessage(new Error('[object Object]'), fallback)).toBe(fallback);
    });

    it('transparently preserves real error messages without loss', () => {
      const err = new Error("Template requires skill 'office-document' which does not exist in the system.");
      expect(extractSummonErrorMessage(err, fallback)).toBe("Template requires skill 'office-document' which does not exist in the system.");

      const authErr = new Error('Authentication required');
      expect(extractSummonErrorMessage(authErr, fallback)).toBe('Authentication required');

      const netErr = new Error('无法连接到服务器，请检查服务是否启动');
      expect(extractSummonErrorMessage(netErr, fallback)).toBe('无法连接到服务器，请检查服务是否启动');
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
