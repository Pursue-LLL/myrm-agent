import { describe, expect, it, vi } from 'vitest';
import {
  getProviderFromModel,
  formatSubCentCost,
  generateUsageCsv,
  downloadUsageCsv,
} from '../usageExport';
import type { UsageStats, DailyUsage } from '@/services/statistics';

describe('usageExport pure deterministic logic', () => {
  it('correctly maps model names to provider categories', () => {
    expect(getProviderFromModel('gpt-4o')).toBe('OpenAI');
    expect(getProviderFromModel('o3-mini')).toBe('OpenAI');
    expect(getProviderFromModel('claude-3-7-sonnet')).toBe('Anthropic');
    expect(getProviderFromModel('deepseek-r1')).toBe('DeepSeek');
    expect(getProviderFromModel('gemini-2.0-flash')).toBe('Google');
    expect(getProviderFromModel('qwen-2.5-coder')).toBe('Qwen/Alibaba');
    expect(getProviderFromModel('ollama/llama3')).toBe('Local/Ollama');
    expect(getProviderFromModel('custom-finetuned')).toBe('Custom/Other');
  });

  it('formats sub-cent costs without lossy rounding to zero', () => {
    expect(formatSubCentCost(0)).toBe('0.00');
    expect(formatSubCentCost(0.0034)).toBe('0.0034');
    expect(formatSubCentCost(0.0008)).toBe('0.0008');
    expect(formatSubCentCost(0.05)).toBe('0.05');
    expect(formatSubCentCost(12.345)).toBe('12.35');
  });

  it('generates well-formed CSV string with model breakdown and daily history', () => {
    const mockStats: UsageStats = {
      calls: 15,
      totalTokens: 25000,
      inputTokens: 20000,
      outputTokens: 5000,
      cachedTokens: 8000,
      reasoningTokens: 1200,
      citationTokens: 0,
      costUsd: 0.0084,
      cacheHitRate: 32.0,
      modelBreakdown: {
        'deepseek-r1': {
          calls: 10,
          totalTokens: 18000,
          inputTokens: 15000,
          outputTokens: 3000,
          cachedTokens: 6000,
          costUsd: 0.0042,
        },
        'gpt-4o': {
          calls: 5,
          totalTokens: 7000,
          inputTokens: 5000,
          outputTokens: 2000,
          cachedTokens: 2000,
          costUsd: 0.0042,
        },
      },
    };

    const mockDaily: DailyUsage[] = [
      {
        date: '2026-10-11',
        calls: 15,
        totalTokens: 25000,
        inputTokens: 20000,
        outputTokens: 5000,
        cachedTokens: 8000,
        reasoningTokens: 0,
        citationTokens: 0,
        costUsd: 0.0084,
        cacheSavingsUsd: 0,
        cacheBreakCounts: {},
      },
    ];

    const csv = generateUsageCsv(mockStats, mockDaily);

    // Verify sections and headers
    expect(csv).toContain('--- SUMMARY ---');
    expect(csv).toContain('Total Calls,Total Tokens,Input Tokens,Output Tokens,Cached Tokens,Total Cost (USD),Cache Hit Rate (%)');
    expect(csv).toContain('15,25000,20000,5000,8000,0.0084,32.00');

    expect(csv).toContain('--- MODEL BREAKDOWN ---');
    expect(csv).toContain('Model,Provider,Calls,Input Tokens,Output Tokens,Cached Tokens,Total Tokens,Cost (USD)');
    expect(csv).toContain('"deepseek-r1","DeepSeek",10,15000,3000,6000,18000,0.0042');
    expect(csv).toContain('"gpt-4o","OpenAI",5,5000,2000,2000,7000,0.0042');

    expect(csv).toContain('--- DAILY HISTORY ---');
    expect(csv).toContain('2026-10-11,15,25000,20000,5000,8000,0.0084');
  });

  it('triggers browser download with blob and anchor link', () => {
    const clickMock = vi.fn();
    const appendChildMock = vi.fn();
    const removeChildMock = vi.fn();

    vi.spyOn(document, 'createElement').mockReturnValue({
      setAttribute: vi.fn(),
      style: {},
      click: clickMock,
    } as unknown as HTMLElement);

    vi.spyOn(document.body, 'appendChild').mockImplementation(appendChildMock);
    vi.spyOn(document.body, 'removeChild').mockImplementation(removeChildMock);

    global.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    global.URL.revokeObjectURL = vi.fn();

    downloadUsageCsv(null, []);

    expect(clickMock).toHaveBeenCalledTimes(1);
    expect(appendChildMock).toHaveBeenCalledTimes(1);
    expect(removeChildMock).toHaveBeenCalledTimes(1);
  });
});
