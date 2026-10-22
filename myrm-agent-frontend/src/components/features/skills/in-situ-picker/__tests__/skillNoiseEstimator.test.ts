import { describe, it, expect } from 'vitest';
import {
  estimateSkillNoise,
  estimateDeltaNoise,
} from '../skillNoiseEstimator';
import { InSituSkillDescriptor } from '../inSituSkillPickerTypes';

describe('skillNoiseEstimator', () => {
  const mockBaseSkill: InSituSkillDescriptor = {
    id: 's1',
    name: 'Skill 1',
    description: 'desc',
    author: 'author',
    stars: 10,
    category: '代码开发',
    toolCount: 3,
    estimatedTokenCost: 500,
    safetyScanStatus: 'clean',
    isMounted: true,
    version: '1.0.0',
    tags: ['tag1'],
  };

  it('未挂载任何技能时动作空间保持 optimal 且仅含底噪', () => {
    const unmountedSkill: InSituSkillDescriptor = {
      ...mockBaseSkill,
      isMounted: false,
    };

    const rating = estimateSkillNoise([unmountedSkill]);
    expect(rating.level).toBe('optimal');
    expect(rating.totalTokens).toBe(600); // 基础底噪
    expect(rating.activeToolsCount).toBe(0);
    expect(rating.score).toBeLessThanOrEqual(20);
  });

  it('挂载少量工具时动作空间处于健康 optimal 状态', () => {
    const rating = estimateSkillNoise([mockBaseSkill]);
    expect(rating.level).toBe('optimal');
    expect(rating.totalTokens).toBe(1100); // 600 + 500
    expect(rating.activeToolsCount).toBe(3);
  });

  it('挂载大量重型技能时正确判定为 crowded 或 overloaded', () => {
    const heavySkills: InSituSkillDescriptor[] = Array.from({ length: 6 }).map(
      (_, i) => ({
        ...mockBaseSkill,
        id: `heavy-${i}`,
        toolCount: 5,
        estimatedTokenCost: 1000,
        isMounted: true,
      })
    );

    const rating = estimateSkillNoise(heavySkills);
    expect(rating.level).toBe('overloaded');
    expect(rating.activeToolsCount).toBe(30);
    expect(rating.totalTokens).toBeGreaterThan(6000);
    expect(rating.score).toBeGreaterThan(80);
  });

  it('estimateDeltaNoise 能够准确预估目标技能挂载后的增量开销', () => {
    const currentMounted: InSituSkillDescriptor[] = [mockBaseSkill];
    const candidateSkill: InSituSkillDescriptor = {
      id: 'candidate-1',
      name: 'Candidate Skill',
      description: 'candidate',
      author: 'author',
      stars: 5,
      category: '数据分析',
      toolCount: 4,
      estimatedTokenCost: 800,
      safetyScanStatus: 'clean',
      isMounted: false,
      version: '1.0.0',
      tags: ['data'],
    };

    const delta = estimateDeltaNoise(currentMounted, candidateSkill);
    expect(delta.before.totalTokens).toBe(1100);
    expect(delta.after.totalTokens).toBe(1900);
    expect(delta.deltaTokens).toBe(800);
    expect(delta.after.activeToolsCount).toBe(7);
  });
});
