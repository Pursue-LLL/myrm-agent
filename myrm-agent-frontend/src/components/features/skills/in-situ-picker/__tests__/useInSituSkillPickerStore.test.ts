import { describe, it, expect, beforeEach } from 'vitest';
import { useInSituSkillPickerStore } from '../useInSituSkillPickerStore';

describe('useInSituSkillPickerStore', () => {
  beforeEach(() => {
    useInSituSkillPickerStore.getState().resetToDefault();
  });

  it('初始状态具备默认技能列表并处于抽屉收起态', () => {
    const state = useInSituSkillPickerStore.getState();
    expect(state.skills.length).toBeGreaterThanOrEqual(5);
    expect(state.isDrawerOpen).toBe(false);
    expect(state.drawerHeight).toBe(480);
  });

  it('toggleMountSkill 能够翻转目标技能的挂载状态', () => {
    const { toggleMountSkill } = useInSituSkillPickerStore.getState();
    const initialSkill = useInSituSkillPickerStore
      .getState()
      .skills.find((s) => s.id === 'skill-excel-analytics');
    expect(initialSkill?.isMounted).toBe(false);

    toggleMountSkill('skill-excel-analytics');

    const updated = useInSituSkillPickerStore
      .getState()
      .skills.find((s) => s.id === 'skill-excel-analytics');
    expect(updated?.isMounted).toBe(true);
  });

  it('setSearchQuery 和 setCategoryFilter 正确驱动技能过滤', () => {
    const { setSearchQuery, setCategoryFilter, getFilteredSkills } =
      useInSituSkillPickerStore.getState();

    setSearchQuery('Excel');
    let filtered = getFilteredSkills();
    expect(filtered.length).toBe(1);
    expect(filtered[0].id).toBe('skill-excel-analytics');

    setSearchQuery('');
    setCategoryFilter('网页检索');
    filtered = getFilteredSkills();
    expect(filtered.length).toBe(1);
    expect(filtered[0].id).toBe('skill-web-scraper-pro');
  });

  it('setDrawerHeight 严格将高度 clamp 在 300 到 760 像素范围内', () => {
    const { setDrawerHeight } = useInSituSkillPickerStore.getState();

    setDrawerHeight(100);
    expect(useInSituSkillPickerStore.getState().drawerHeight).toBe(300);

    setDrawerHeight(999);
    expect(useInSituSkillPickerStore.getState().drawerHeight).toBe(760);

    setDrawerHeight(520);
    expect(useInSituSkillPickerStore.getState().drawerHeight).toBe(520);
  });

  it('setHoveredSkillId 驱动 getPreviewNoiseDelta 提供悬停增量预估', () => {
    const { setHoveredSkillId, getPreviewNoiseDelta } =
      useInSituSkillPickerStore.getState();

    // 针对未挂载的 Excel 技能
    setHoveredSkillId('skill-excel-analytics');
    const delta = getPreviewNoiseDelta();
    expect(delta).not.toBeNull();
    if (delta) {
      expect(delta.deltaTokens).toBe(520);
      expect(delta.after.totalTokens).toBeGreaterThan(delta.before.totalTokens);
    }

    // 针对已挂载的技能或清除悬停时应返回 null
    setHoveredSkillId('skill-python-interpreter');
    expect(getPreviewNoiseDelta()).toBeNull();

    setHoveredSkillId(null);
    expect(getPreviewNoiseDelta()).toBeNull();
  });

  describe('handleIncomingPostMessage 跨窗口通信安全协议', () => {
    it('拒绝非白名单 Origin 的恶意消息', () => {
      const { handleIncomingPostMessage } = useInSituSkillPickerStore.getState();
      const maliciousEvent = new MessageEvent('message', {
        origin: 'https://evil-attacker.com',
        data: {
          type: 'myrm-skill-pick',
          identifier: 'malicious-skill',
        },
      });

      const handled = handleIncomingPostMessage(maliciousEvent);
      expect(handled).toBe(false);
    });

    it('合法 Origin 下能将匹配的已有技能直接切换为挂载态', () => {
      const { handleIncomingPostMessage } = useInSituSkillPickerStore.getState();
      const validEvent = new MessageEvent('message', {
        origin: 'https://docs.myrm.internal',
        data: {
          type: 'myrm-skill-pick',
          identifier: 'skill-excel-analytics',
          name: 'Excel 与报表深度分析 (Excel Analytics)',
        },
      });

      const handled = handleIncomingPostMessage(validEvent);
      expect(handled).toBe(true);

      const skill = useInSituSkillPickerStore
        .getState()
        .skills.find((s) => s.id === 'skill-excel-analytics');
      expect(skill?.isMounted).toBe(true);
    });

    it('合法 Origin 下若是外部 Hub 新技能则动态注册并挂载', () => {
      const { handleIncomingPostMessage } = useInSituSkillPickerStore.getState();
      const dynamicEvent = new MessageEvent('message', {
        origin: 'https://skills.myrm.internal',
        data: {
          type: 'myrm-skill-pick',
          identifier: 'hub-k8s-operator',
          name: 'Kubernetes Cluster Operator',
          installCmd: 'myrm skill install k8s-operator',
          source: 'Official Hub',
        },
      });

      const handled = handleIncomingPostMessage(dynamicEvent);
      expect(handled).toBe(true);

      const dynamicSkill = useInSituSkillPickerStore
        .getState()
        .skills.find((s) => s.id === 'hub-k8s-operator');
      expect(dynamicSkill).toBeDefined();
      expect(dynamicSkill?.isMounted).toBe(true);
      expect(dynamicSkill?.installCmd).toBe('myrm skill install k8s-operator');
    });
  });
});
