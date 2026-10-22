import { describe, it, expect, beforeEach } from 'vitest';
import { useBotCreatorStudioStore } from '../useBotCreatorStudioStore';

describe('useBotCreatorStudioStore', () => {
  beforeEach(() => {
    useBotCreatorStudioStore.getState().resetStudioForm();
    useBotCreatorStudioStore.getState().closeStudio();
  });

  it('initializes with default closed state and default form values', () => {
    const state = useBotCreatorStudioStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.form.isInheritingMaster).toBe(true);
    expect(state.form.selectedTier).toBe('deep_reasoning');
    expect(state.availableMascots.length).toBeGreaterThan(0);
  });

  it('opens studio and updates form fields', () => {
    useBotCreatorStudioStore.getState().openStudio();
    expect(useBotCreatorStudioStore.getState().isOpen).toBe(true);

    useBotCreatorStudioStore.getState().updateFormField('botName', '售前咨询专家');
    useBotCreatorStudioStore.getState().updateFormField('roleDescription', '线索挖掘');

    const state = useBotCreatorStudioStore.getState();
    expect(state.form.botName).toBe('售前咨询专家');
    expect(state.form.roleDescription).toBe('线索挖掘');
  });

  it('toggles master inheritance and fine-grained options', () => {
    useBotCreatorStudioStore.getState().openStudio();
    useBotCreatorStudioStore.getState().toggleInheritance(false);
    expect(useBotCreatorStudioStore.getState().form.isInheritingMaster).toBe(false);

    useBotCreatorStudioStore.getState().toggleInheritance(true);
    expect(useBotCreatorStudioStore.getState().form.isInheritingMaster).toBe(true);

    useBotCreatorStudioStore.getState().toggleInheritanceOption('inheritTools', false);
    expect(useBotCreatorStudioStore.getState().form.inheritanceOptions.inheritTools).toBe(false);
  });

  it('selects cognitive tier and selects pixel mascot', () => {
    useBotCreatorStudioStore.getState().openStudio();
    useBotCreatorStudioStore.getState().selectCognitiveTier('fast_flash');
    expect(useBotCreatorStudioStore.getState().form.selectedTier).toBe('fast_flash');

    useBotCreatorStudioStore.getState().selectPixelMascot('mascot_shiba_inu');
    const state = useBotCreatorStudioStore.getState();
    expect(state.form.selectedMascotId).toBe('mascot_shiba_inu');
    expect(state.form.avatarType).toBe('pixel_mascot');
  });

  it('generates AI avatar asynchronously', async () => {
    useBotCreatorStudioStore.getState().openStudio();
    await useBotCreatorStudioStore.getState().generateAiAvatar();

    const state = useBotCreatorStudioStore.getState();
    expect(state.form.avatarType).toBe('ai_generated');
    expect(state.form.generatedAvatarUrl).toContain('https://assets.myrm.ai/avatars/');
  });

  it('submits and creates bot summary', async () => {
    useBotCreatorStudioStore.getState().openStudio();
    useBotCreatorStudioStore.getState().updateFormField('botName', '代码守卫');

    const created = await useBotCreatorStudioStore.getState().submitCreateBot();
    expect(created.name).toBe('代码守卫');
    expect(created.inheritedToolsCount).toBeGreaterThan(0);
    expect(useBotCreatorStudioStore.getState().isOpen).toBe(false);
    expect(useBotCreatorStudioStore.getState().lastCreatedBot).toEqual(created);
  });
});
