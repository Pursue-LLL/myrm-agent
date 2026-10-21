import { describe, it, expect, beforeEach } from 'vitest';
import { useConversationalOnboardingStore } from '../useConversationalOnboardingStore';

describe('useConversationalOnboardingStore', () => {
  beforeEach(() => {
    useConversationalOnboardingStore.getState().resetOnboarding();
  });

  it('initializes with default welcome message and ready launcher services', () => {
    const state = useConversationalOnboardingStore.getState();
    expect(state.step).toBe('intent_selection');
    expect(state.messages.length).toBe(1);
    expect(state.activeRecipeDraft).toBeNull();
    expect(state.launcherServices.length).toBe(3);
    expect(state.launcherServices.every((s) => s.isReady)).toBe(true);
    expect(state.isCompleted).toBe(false);
  });

  it('selects preset intent and auto-generates recipe draft', () => {
    const store = useConversationalOnboardingStore.getState();
    store.selectPresetIntent('marketing');

    const updated = useConversationalOnboardingStore.getState();
    expect(updated.step).toBe('recipe_preview');
    expect(updated.activeRecipeDraft).not.toBeNull();
    expect(updated.activeRecipeDraft?.presetKey).toBe('marketing');
    expect(updated.activeRecipeDraft?.suggestedName).toBe('增长与营销洞察官');
    expect(updated.messages.length).toBe(3); // 1 initial + 1 user reply + 1 assistant follow-up
  });

  it('submits natural language input and dynamically infers custom recipe', () => {
    const store = useConversationalOnboardingStore.getState();
    store.submitUserInput('我想做一个能自动帮我修 bug、跑单元测试的助手');

    const updated = useConversationalOnboardingStore.getState();
    expect(updated.step).toBe('recipe_preview');
    expect(updated.activeRecipeDraft?.presetKey).toBe('software_eng');
    expect(updated.activeRecipeDraft?.recommendedModelTier).toBe('pro');
    expect(updated.messages.length).toBe(3);
  });

  it('toggles skill selection in active recipe draft', () => {
    const store = useConversationalOnboardingStore.getState();
    store.selectPresetIntent('software_eng');

    let draft = useConversationalOnboardingStore.getState().activeRecipeDraft;
    const gitSkill = draft?.recommendedSkills.find((s) => s.id === 'skill_git_tools');
    expect(gitSkill?.selected).toBe(true);

    // 切换取消勾选
    store.toggleSkillSelection('skill_git_tools');
    draft = useConversationalOnboardingStore.getState().activeRecipeDraft;
    const updatedGitSkill = draft?.recommendedSkills.find((s) => s.id === 'skill_git_tools');
    expect(updatedGitSkill?.selected).toBe(false);

    // 再次切换重新勾选
    store.toggleSkillSelection('skill_git_tools');
    draft = useConversationalOnboardingStore.getState().activeRecipeDraft;
    expect(draft?.recommendedSkills.find((s) => s.id === 'skill_git_tools')?.selected).toBe(true);
  });

  it('updates recipe draft fields and completes onboarding', () => {
    const store = useConversationalOnboardingStore.getState();
    store.selectPresetIntent('admin_writing');

    store.updateRecipeDraft({
      suggestedName: '个性化定制行政小蜜',
      recommendedModelTier: 'pro',
    });

    const draft = useConversationalOnboardingStore.getState().activeRecipeDraft;
    expect(draft?.suggestedName).toBe('个性化定制行政小蜜');
    expect(draft?.recommendedModelTier).toBe('pro');

    const result = store.applyRecipeAndComplete();
    expect(result.success).toBe(true);
    expect(result.createdAgentId.startsWith('agent_onboarded_')).toBe(true);

    const finishedState = useConversationalOnboardingStore.getState();
    expect(finishedState.isCompleted).toBe(true);
    expect(finishedState.step).toBe('completed');
  });
});
