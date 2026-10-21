import { describe, it, expect, beforeEach } from 'vitest';
import { useSideTrackStore } from '../useSideTrackStore';
import { ReadOnlyCodeSnapshot, ReadOnlyStepSnapshot } from '../sideTrackTypes';

describe('useSideTrackStore', () => {
  beforeEach(() => {
    useSideTrackStore.getState().clearSession();
  });

  const mockStep: ReadOnlyStepSnapshot = {
    stepId: 'step-01',
    stepTitle: '生成并挂载前端分屏抽屉',
    toolAction: 'build_component',
  };

  const mockCode: ReadOnlyCodeSnapshot = {
    filePath: 'src/components/Drawer.tsx',
    codeSnippet: 'export const Drawer = () => <div>Drawer</div>;',
    language: 'typescript',
  };

  it('initializes with default closed state', () => {
    const state = useSideTrackStore.getState();
    expect(state.isDrawerOpen).toBe(false);
    expect(state.activeSession).toBeNull();
    expect(state.selectedCodeSnapshot).toBeNull();
  });

  it('opens side track session and mounts code snapshots', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-123456', '构建前端组件库', mockStep, [mockCode]);

    const state = useSideTrackStore.getState();
    expect(state.isDrawerOpen).toBe(true);
    expect(state.activeSession).not.toBeNull();
    expect(state.activeSession?.mainSessionId).toBe('main-123456');
    expect(state.activeSession?.snapshot.mainTaskName).toBe('构建前端组件库');
    expect(state.selectedCodeSnapshot?.filePath).toBe('src/components/Drawer.tsx');
  });

  it('toggles and closes drawer correctly', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-123456', '构建前端组件库', mockStep);

    expect(useSideTrackStore.getState().isDrawerOpen).toBe(true);

    useSideTrackStore.getState().closeSideTrack();
    expect(useSideTrackStore.getState().isDrawerOpen).toBe(false);

    useSideTrackStore.getState().toggleDrawer(true);
    expect(useSideTrackStore.getState().isDrawerOpen).toBe(true);

    useSideTrackStore.getState().toggleDrawer();
    expect(useSideTrackStore.getState().isDrawerOpen).toBe(false);
  });

  it('selects active code snapshot for inspection', () => {
    const anotherCode: ReadOnlyCodeSnapshot = {
      filePath: 'src/utils/engine.ts',
      codeSnippet: 'export const run = () => {};',
      language: 'typescript',
    };

    useSideTrackStore
      .getState()
      .openSideTrack('main-123456', '构建前端组件库', mockStep, [
        mockCode,
        anotherCode,
      ]);

    expect(useSideTrackStore.getState().selectedCodeSnapshot?.filePath).toBe(
      'src/components/Drawer.tsx'
    );

    useSideTrackStore.getState().selectCodeSnapshot(anotherCode);
    expect(useSideTrackStore.getState().selectedCodeSnapshot?.filePath).toBe(
      'src/utils/engine.ts'
    );
  });

  it('sends user inquiry and generates assistant explanation without mutating main state', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-123456', '构建前端组件库', mockStep, [mockCode]);

    useSideTrackStore.getState().sendInquiry('分析并发安全');

    const session = useSideTrackStore.getState().activeSession;
    expect(session?.messages.length).toBe(3); // system, user, assistant
    expect(session?.messages[1].sender).toBe('user');
    expect(session?.messages[1].content).toBe('分析并发安全');
    expect(session?.messages[2].sender).toBe('assistant');
    expect(session?.messages[2].content).toContain('并发');
    expect(session?.status).toBe('idle');
  });

  it('ignores empty query and inquiry when no session is active', () => {
    useSideTrackStore.getState().sendInquiry('   ');
    expect(useSideTrackStore.getState().activeSession).toBeNull();
  });
});
