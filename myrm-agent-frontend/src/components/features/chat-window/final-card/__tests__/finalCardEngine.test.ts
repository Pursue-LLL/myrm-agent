import { describe, it, expect } from 'vitest';
import {
  formatDurationText,
  formatSizeBytes,
  assembleFinalCardContract,
  validateFinalCardContract,
} from '../finalCardEngine';

describe('finalCardEngine', () => {
  describe('formatDurationText', () => {
    it('handles non-positive duration', () => {
      expect(formatDurationText(0)).toBe('0s');
      expect(formatDurationText(-100)).toBe('0s');
    });

    it('formats millisecond intervals', () => {
      expect(formatDurationText(450)).toBe('450ms');
      expect(formatDurationText(999)).toBe('999ms');
    });

    it('formats seconds intervals', () => {
      expect(formatDurationText(1000)).toBe('1.0s');
      expect(formatDurationText(5500)).toBe('5.5s');
      expect(formatDurationText(59900)).toBe('59.9s');
    });

    it('formats minute and second combinations', () => {
      expect(formatDurationText(60000)).toBe('1m 0s');
      expect(formatDurationText(125000)).toBe('2m 5s');
    });
  });

  describe('formatSizeBytes', () => {
    it('handles undefined or 0 bytes', () => {
      expect(formatSizeBytes()).toBe('0 B');
      expect(formatSizeBytes(0)).toBe('0 B');
      expect(formatSizeBytes(-50)).toBe('0 B');
    });

    it('formats bytes below 1KB', () => {
      expect(formatSizeBytes(512)).toBe('512 B');
      expect(formatSizeBytes(1023)).toBe('1023 B');
    });

    it('formats kilobytes', () => {
      expect(formatSizeBytes(1024)).toBe('1.0 KB');
      expect(formatSizeBytes(1536)).toBe('1.5 KB');
      expect(formatSizeBytes(1024 * 500)).toBe('500.0 KB');
    });

    it('formats megabytes', () => {
      expect(formatSizeBytes(1024 * 1024)).toBe('1.0 MB');
      expect(formatSizeBytes(1024 * 1024 * 3.5)).toBe('3.5 MB');
    });
  });

  describe('assembleFinalCardContract', () => {
    it('assembles a default contract with minimal params', () => {
      const contract = assembleFinalCardContract({
        turnId: 'turn-100',
        title: '构建成功',
        summary: '产物已打包完毕',
      });

      expect(contract.turnId).toBe('turn-100');
      expect(contract.title).toBe('构建成功');
      expect(contract.status).toBe('completed');
      expect(contract.transcriptUrl).toBe('/api/transcripts/turn-100');
      expect(contract.rawLogLinesCount).toBe(0);
      expect(contract.keyDecisions).toEqual([]);
      expect(contract.artifacts).toEqual([]);
      expect(contract.actionOptions).toEqual([]);
      expect(contract.id.startsWith('final_card_turn-100_')).toBe(true);
    });

    it('assembles a rich contract with complete parameters', () => {
      const contract = assembleFinalCardContract({
        turnId: 'turn-200',
        title: '测试完成',
        summary: '30 组用例已全部通过',
        status: 'partial_success',
        keyDecisions: ['采用内存数据库'],
        artifacts: [{ id: 'a1', name: 'report.json', type: 'document', path: '/report.json', previewable: false }],
        actionOptions: [{ id: 'o1', label: '重试', actionKind: 'run_tests' }],
        executionDurationMs: 3200,
        tokensUsed: { prompt: 100, completion: 200, total: 300 },
        transcriptUrl: '/custom/transcript/url',
        rawLogsPreview: ['line1', 'line2', 'line3'],
      });

      expect(contract.status).toBe('partial_success');
      expect(contract.rawLogLinesCount).toBe(3);
      expect(contract.transcriptUrl).toBe('/custom/transcript/url');
      expect(contract.tokensUsed?.total).toBe(300);
      expect(contract.keyDecisions).toEqual(['采用内存数据库']);
    });
  });

  describe('validateFinalCardContract', () => {
    it('validates a valid assembled contract', () => {
      const contract = assembleFinalCardContract({
        turnId: 'turn-300',
        title: '交付卡片',
        summary: '一切就绪',
      });

      const result = validateFinalCardContract(contract);
      expect(result.valid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    it('catches non-object inputs', () => {
      expect(validateFinalCardContract(null).valid).toBe(false);
      expect(validateFinalCardContract('string').valid).toBe(false);
      expect(validateFinalCardContract(123).valid).toBe(false);
    });

    it('catches missing or invalid fields', () => {
      const invalidContract = {
        id: '',
        turnId: '',
        title: '',
        summary: 123,
        keyDecisions: 'not-array',
        artifacts: null,
        actionOptions: false,
        transcriptUrl: '',
      };

      const result = validateFinalCardContract(invalidContract);
      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThanOrEqual(8);
    });
  });
});
