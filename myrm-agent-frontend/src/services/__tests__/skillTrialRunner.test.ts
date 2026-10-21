import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getSkillSmokeTestPrompt, launchSkillTrialRun } from '../skillTrialRunner';
import useChatStore from '@/store/useChatStore';

describe('skillTrialRunner', () => {
  beforeEach(() => {
    useChatStore.setState({ inputMessage: '' });
  });

  it('returns explicit examplePrompt if provided', () => {
    const prompt = getSkillSmokeTestPrompt({
      skillId: 'custom-skill',
      skillName: 'Custom Skill',
      examplePrompt: 'Custom prompt text',
    });
    expect(prompt).toBe('Custom prompt text');
  });

  it('returns specialized template for known skills', () => {
    const zhPrompt = getSkillSmokeTestPrompt({
      skillId: 'host-server-ops',
      skillName: 'Host Ops Health',
      lang: 'zh',
    });
    expect(zhPrompt).toContain('host-server-ops');
    expect(zhPrompt).toContain('巡检');

    const enPrompt = getSkillSmokeTestPrompt({
      skillId: 'office-document',
      skillName: 'Office Document',
      lang: 'en',
    });
    expect(enPrompt).toContain('office-document');
    expect(enPrompt).toContain('Excel');
  });

  it('falls back to generic template for unknown skills', () => {
    const zhPrompt = getSkillSmokeTestPrompt({
      skillId: 'my-custom-parser',
      skillName: 'My Custom Parser',
      lang: 'zh',
    });
    expect(zhPrompt).toContain('【My Custom Parser】');
    expect(zhPrompt).toContain('冒烟试跑');
  });

  it('launchSkillTrialRun updates store inputMessage and calls onNavigate', () => {
    const navigateSpy = vi.fn();
    const resultPrompt = launchSkillTrialRun({
      skillId: 'deep-research',
      skillName: 'Deep Research',
      onNavigate: navigateSpy,
    });

    expect(resultPrompt).toContain('deep-research');
    expect(useChatStore.getState().inputMessage).toBe(resultPrompt);
    expect(navigateSpy).toHaveBeenCalledTimes(1);
  });
});
