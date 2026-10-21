import { describe, it, expect } from 'vitest';
import {
  DEFAULT_ARENA_MODELS,
  createInitialStreamState,
  buildSynthesizePrompt,
  validateLocalProjectPath,
  calculateDiffSimilarity,
} from '../arenaEngine';
import type { ArenaModelStream } from '../arenaTypes';

describe('arenaEngine', () => {
  it('预设模型列表应包含不同厂商与推理能力等级的模型', () => {
    expect(DEFAULT_ARENA_MODELS.length).toBeGreaterThanOrEqual(4);
    const claude = DEFAULT_ARENA_MODELS.find((m) => {
      return m.id === 'claude-3-7-thinking';
    });
    const deepseek = DEFAULT_ARENA_MODELS.find((m) => {
      return m.id === 'deepseek-r1';
    });

    expect(claude).toBeDefined();
    expect(deepseek).toBeDefined();
    if (claude && deepseek) {
      expect(claude.tier).toBe('reasoning');
      expect(deepseek.tier).toBe('reasoning');
    }
  });

  describe('createInitialStreamState', () => {
    it('应初始化为空闲态并赋予正确的模型 ID', () => {
      const stream = createInitialStreamState('gpt-4o');
      expect(stream.modelId).toBe('gpt-4o');
      expect(stream.status).toBe('idle');
      expect(stream.contentText).toBe('');
      expect(stream.latencyMs).toBe(0);
    });
  });

  describe('buildSynthesizePrompt', () => {
    it('能正确拼装包含多模型输出的合成 Prompt', () => {
      const mockStreams: ArenaModelStream[] = [
        {
          modelId: 'claude-3-7-thinking',
          status: 'completed',
          contentText: '方案 A：采用异步事件驱动架构',
          latencyMs: 1200,
          tokenCount: 450,
        },
        {
          modelId: 'deepseek-r1',
          status: 'completed',
          contentText: '方案 B：引入内存预分配池优化吞吐',
          latencyMs: 950,
          tokenCount: 380,
        },
      ];

      const prompt = buildSynthesizePrompt('如何优化高并发网关？', mockStreams);
      expect(prompt).toContain('如何优化高并发网关？');
      expect(prompt).toContain('【模型输出 1 (claude-3-7-thinking)】:');
      expect(prompt).toContain('方案 A：采用异步事件驱动架构');
      expect(prompt).toContain('【模型输出 2 (deepseek-r1)】:');
      expect(prompt).toContain('方案 B：引入内存预分配池优化吞吐');
    });
  });

  describe('validateLocalProjectPath', () => {
    it('空路径应返回错误', () => {
      const res = validateLocalProjectPath('   ');
      expect(res.isValid).toBe(false);
      expect(res.error).toBe('项目路径不能为空');
    });

    it('包含非法字符或相对路径应拒绝', () => {
      expect(validateLocalProjectPath('../my-project').isValid).toBe(false);
      expect(validateLocalProjectPath('some/relative/path').isValid).toBe(false);
    });

    it('合法绝对路径或 ~ 目录应成功标准化', () => {
      const res1 = validateLocalProjectPath('~/projects/ai-hub');
      expect(res1.isValid).toBe(true);
      expect(res1.normalizedPath).toBe('~/projects/ai-hub');

      const res2 = validateLocalProjectPath('/Users/developer/code');
      expect(res2.isValid).toBe(true);
      expect(res2.normalizedPath).toBe('/Users/developer/code');
    });
  });

  describe('calculateDiffSimilarity', () => {
    it('相同内容应返回 100% 相似度', () => {
      const res = calculateDiffSimilarity('const a = 1;', 'const a = 1;');
      expect(res.similarityPercentage).toBe(100);
      expect(res.charDiffCount).toBe(0);
    });

    it('不同长度内容应计算字符差与相似度估算', () => {
      const res = calculateDiffSimilarity('hello world', 'hello');
      expect(res.charDiffCount).toBe(6);
      expect(res.similarityPercentage).toBeLessThan(100);
    });
  });
});
