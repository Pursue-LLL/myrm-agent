import { describe, it, expect, beforeEach } from 'vitest';
import { useOnDemandConfirmationStore } from '../useOnDemandConfirmationStore';
import { OnDemandDecisionInterrupt } from '../onDemandConfirmationTypes';

describe('useOnDemandConfirmationStore 状态单测', () => {
  const sampleInterrupt: OnDemandDecisionInterrupt = {
    interruptId: 'int-201',
    taskId: 'task-888',
    prompt: '选择小红书图文文案风格',
    options: [
      { id: 'A', label: '干货专业风' },
      { id: 'B', label: '情绪种草风', isRecommended: true },
      { id: 'C', label: '极简测评风' },
    ],
  };

  beforeEach(() => {
    useOnDemandConfirmationStore.setState({
      currentInterrupt: null,
      selectedOptionId: null,
      customInput: '',
      isModalOpen: false,
      historyDecisions: [],
      activeNavEntryId: 'main_chat',
    });
  });

  it('setInterrupt 自动打开弹窗并优先选中带 isRecommended 的推荐选项', () => {
    useOnDemandConfirmationStore.getState().setInterrupt(sampleInterrupt);

    const state = useOnDemandConfirmationStore.getState();
    expect(state.isModalOpen).toBe(true);
    expect(state.currentInterrupt?.interruptId).toBe('int-201');
    expect(state.selectedOptionId).toBe('B'); // 自动选中推荐项 B
  });

  it('selectOption 与 setCustomInput 能正确更新状态', () => {
    useOnDemandConfirmationStore.getState().setInterrupt(sampleInterrupt);
    useOnDemandConfirmationStore.getState().selectOption('A');
    useOnDemandConfirmationStore.getState().setCustomInput('重点突出续航参数');

    const state = useOnDemandConfirmationStore.getState();
    expect(state.selectedOptionId).toBe('A');
    expect(state.customInput).toBe('重点突出续航参数');
  });

  it('confirmDecision 生成结果并入库 historyDecisions，同时清空当前中断', () => {
    useOnDemandConfirmationStore.getState().setInterrupt(sampleInterrupt);
    useOnDemandConfirmationStore.getState().selectOption('C');
    useOnDemandConfirmationStore.getState().setCustomInput('补充竞品对比');

    const result = useOnDemandConfirmationStore.getState().confirmDecision();

    expect(result).not.toBeNull();
    if (result) {
      expect(result.selectedOptionId).toBe('C');
      expect(result.customInput).toBe('补充竞品对比');
    }

    const state = useOnDemandConfirmationStore.getState();
    expect(state.isModalOpen).toBe(false);
    expect(state.currentInterrupt).toBeNull();
    expect(state.historyDecisions.length).toBe(1);
    expect(state.historyDecisions[0].selectedOptionId).toBe('C');
  });

  it('setActiveNavEntryId 能正确切换九大导航当前选中项', () => {
    useOnDemandConfirmationStore.getState().setActiveNavEntryId('cron_jobs');
    expect(useOnDemandConfirmationStore.getState().activeNavEntryId).toBe('cron_jobs');

    useOnDemandConfirmationStore.getState().setActiveNavEntryId('skills_mcp');
    expect(useOnDemandConfirmationStore.getState().activeNavEntryId).toBe('skills_mcp');
  });
});
