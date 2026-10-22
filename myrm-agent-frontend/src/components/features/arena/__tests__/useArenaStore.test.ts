import { describe, it, expect, beforeEach } from 'vitest';
import { useArenaStore } from '../useArenaStore';

describe('useArenaStore', () => {
  beforeEach(() => {
    useArenaStore.getState().resetStore();
  });

  it('初始状态应正确配置默认竞技场模型与 2 分栏布局', () => {
    const state = useArenaStore.getState();
    expect(state.isArenaMode).toBe(false);
    expect(state.selectedModelIds).toEqual(['claude-3-7-thinking', 'deepseek-r1']);
    expect(state.layoutMode).toBe('split_2');
    expect(state.streamMap['claude-3-7-thinking']).toBeDefined();
    expect(state.streamMap['deepseek-r1']).toBeDefined();
  });

  it('toggleArenaMode 能正确切换竞技场模式', () => {
    const store = useArenaStore.getState();
    store.toggleArenaMode(true);
    expect(useArenaStore.getState().isArenaMode).toBe(true);

    store.toggleArenaMode();
    expect(useArenaStore.getState().isArenaMode).toBe(false);
  });

  it('setSelectedModels 选定 3 个模型时应自动适配为 split_3 布局', () => {
    const store = useArenaStore.getState();
    store.setSelectedModels(['claude-3-7-thinking', 'deepseek-r1', 'gpt-4o']);

    const state = useArenaStore.getState();
    expect(state.selectedModelIds.length).toBe(3);
    expect(state.layoutMode).toBe('split_3');
    expect(state.streamMap['gpt-4o']).toBeDefined();
  });

  it('updateStream 能更新指定模型的流式内容与延迟指标', () => {
    const store = useArenaStore.getState();
    store.updateStream('claude-3-7-thinking', {
      status: 'streaming',
      contentText: '部分生成内容...',
      latencyMs: 320,
    });

    const stream = useArenaStore.getState().streamMap['claude-3-7-thinking'];
    expect(stream?.status).toBe('streaming');
    expect(stream?.contentText).toBe('部分生成内容...');
    expect(stream?.latencyMs).toBe(320);
  });

  it('adoptSingleSolution 能记录单模型权威采纳结果', () => {
    const store = useArenaStore.getState();
    store.updateStream('deepseek-r1', {
      contentText: '深度思考后的最终算法产物',
    });
    store.adoptSingleSolution('deepseek-r1');

    const state = useArenaStore.getState();
    expect(state.adoptedDecision?.chosenModelId).toBe('deepseek-r1');
    expect(state.adoptedDecision?.mode).toBe('adopt_single');
    expect(state.adoptedDecision?.synthesizedContent).toBe('深度思考后的最终算法产物');
  });

  it('synthesizeSolutions 能融合生成长板终极方案', () => {
    const store = useArenaStore.getState();
    store.synthesizeSolutions('融合后的长板方案内容');

    const state = useArenaStore.getState();
    expect(state.adoptedDecision?.chosenModelId).toBe('synthesized');
    expect(state.adoptedDecision?.mode).toBe('synthesize');
    expect(state.adoptedDecision?.synthesizedContent).toBe('融合后的长板方案内容');
  });

  it('bindLocalProject 能校验路径并绑定物理目录', () => {
    const store = useArenaStore.getState();
    const success = store.bindLocalProject('~/projects/myrm-workspace', '全栈项目');
    expect(success).toBe(true);

    const project = useArenaStore.getState().localProject;
    expect(project).toBeDefined();
    if (project) {
      expect(project.isBound).toBe(true);
      expect(project.projectName).toBe('全栈项目');
      expect(project.projectPath).toBe('~/projects/myrm-workspace');
    }

    store.unbindLocalProject();
    expect(useArenaStore.getState().localProject).toBeNull();
  });
});
