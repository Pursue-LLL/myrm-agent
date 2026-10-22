import { describe, it, expect, beforeEach } from 'vitest';
import { useSkillStarterWizardStore } from '../useSkillStarterWizardStore';

describe('useSkillStarterWizardStore', () => {
  beforeEach(() => {
    useSkillStarterWizardStore.getState().resetWizardState();
  });

  it('initializes with closed state', () => {
    const state = useSkillStarterWizardStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.activeSkill).toBeNull();
    expect(state.trialRun.status).toBe('idle');
    expect(state.cronBlueprint.isEnabled).toBe(false);
  });

  it('opens wizard with wechat group summary preset and populates defaults', () => {
    useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    const state = useSkillStarterWizardStore.getState();

    expect(state.isOpen).toBe(true);
    expect(state.activeSkill?.skillId).toBe('wechat_group_summary');
    expect(state.sniffedResources.length).toBeGreaterThan(0);
    expect(state.selectedResourceId).toBe(state.sniffedResources[0].id);
    expect(state.formValues.time_window).toBe('yesterday_full_day');
    expect(state.formValues.business_perspective).toBe('owner_governance');
    expect(state.cronBlueprint.humanReadableTime).toBe('每天早上 08:00');
  });

  it('updates form values correctly', () => {
    useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    useSkillStarterWizardStore.getState().setFormValue('business_perspective', 'sales_leads');

    const state = useSkillStarterWizardStore.getState();
    expect(state.formValues.business_perspective).toBe('sales_leads');
  });

  it('selects resource and syncs with formValues', () => {
    useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    useSkillStarterWizardStore.getState().selectResource('wx_grp_fullstack_dev');

    const state = useSkillStarterWizardStore.getState();
    expect(state.selectedResourceId).toBe('wx_grp_fullstack_dev');
    expect(state.formValues.target_group).toBe('wx_grp_fullstack_dev');
  });

  it('refreshes sniffer resources', async () => {
    useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    await useSkillStarterWizardStore.getState().refreshSniffer();

    const state = useSkillStarterWizardStore.getState();
    expect(state.isSniffing).toBe(false);
    expect(state.sniffedResources.length).toBeGreaterThan(0);
  });

  it('executes trial run and produces summary preview', async () => {
    useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    await useSkillStarterWizardStore.getState().executeTrialRun();

    const state = useSkillStarterWizardStore.getState();
    expect(state.trialRun.status).toBe('success');
    expect(state.trialRun.summaryPreview).toContain('试跑产物预览');
    expect(state.trialRun.extractedItemsCount).toBe(142);
  });

  it('toggles cron hosting and updates target channel', async () => {
    useSkillStarterWizardStore.getState().openWizard('wechat_group_summary');
    await useSkillStarterWizardStore.getState().toggleCronHosting(true);

    let state = useSkillStarterWizardStore.getState();
    expect(state.cronBlueprint.isEnabled).toBe(true);
    expect(state.cronBlueprint.scheduledJobId).toBeDefined();

    useSkillStarterWizardStore.getState().updateTargetChannel('desktop_notification');
    state = useSkillStarterWizardStore.getState();
    expect(state.cronBlueprint.targetChannel).toBe('desktop_notification');

    await useSkillStarterWizardStore.getState().toggleCronHosting(false);
    state = useSkillStarterWizardStore.getState();
    expect(state.cronBlueprint.isEnabled).toBe(false);
    expect(state.cronBlueprint.scheduledJobId).toBeUndefined();
  });
});
