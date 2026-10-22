import { describe, it, expect, beforeEach } from 'vitest';
import {
  useClarificationGateStore,
  detectAmbiguity,
} from '../useClarificationGateStore';

describe('useClarificationGateStore', () => {
  beforeEach(() => {
    useClarificationGateStore.getState().resetState();
  });

  describe('detectAmbiguity', () => {
    it('returns false for empty text', () => {
      expect(detectAmbiguity('')).toBe(false);
      expect(detectAmbiguity('   ')).toBe(false);
    });

    it('returns true when text includes /grill-me', () => {
      expect(detectAmbiguity('/grill-me 帮我看看')).toBe(true);
      expect(detectAmbiguity('请帮我理一下思路 /GRILL-ME')).toBe(true);
    });

    it('returns true for short texts with ambitious action keywords', () => {
      expect(detectAmbiguity('帮我做个落地页')).toBe(true);
      expect(detectAmbiguity('构建一个同步脚本')).toBe(true);
      expect(detectAmbiguity('重构后端系统')).toBe(true);
      expect(detectAmbiguity('build a landing page')).toBe(true);
    });

    it('returns false for detailed long prompts', () => {
      const detailed =
        '请在 src/utils/date.ts 中增加一个 formatDateToIso 函数，入参为 Date 对象，返回值要求严格符合 ISO 8601 标准，并附带两个单元测试。';
      expect(detectAmbiguity(detailed)).toBe(false);
    });
  });

  describe('state machine actions', () => {
    it('opens and closes clarification gate', () => {
      const store = useClarificationGateStore.getState();
      expect(store.isOpen).toBe(false);

      store.openGate('做个落地页', 'button');
      const state1 = useClarificationGateStore.getState();
      expect(state1.isOpen).toBe(true);
      expect(state1.rawInput).toBe('做个落地页');

      store.closeGate();
      expect(useClarificationGateStore.getState().isOpen).toBe(false);
    });

    it('toggles single and multi-select options', () => {
      const store = useClarificationGateStore.getState();
      store.openGate('构建系统', 'auto');

      // 单选测试 (q_platform)
      store.toggleOption('q_platform', 'desktop', false);
      expect(useClarificationGateStore.getState().answers['q_platform']).toEqual(['desktop']);

      store.toggleOption('q_platform', 'server', false);
      expect(useClarificationGateStore.getState().answers['q_platform']).toEqual(['server']);

      // 多选测试 (q_deliverable)
      store.toggleOption('q_deliverable', 'api_contract', true);
      const multi = useClarificationGateStore.getState().answers['q_deliverable'] ?? [];
      expect(multi.includes('api_contract')).toBe(true);
    });

    it('generates fallback spec when skipped by user', () => {
      const store = useClarificationGateStore.getState();
      store.openGate('设计文件服务', 'command');

      const spec = store.skipClarification();
      expect(spec.isSkippedByUser).toBe(true);
      expect(spec.rawPrompt).toBe('设计文件服务');
      expect(spec.assumptionsByModel.length).toBeGreaterThanOrEqual(1);
      expect(useClarificationGateStore.getState().isOpen).toBe(false);
    });

    it('compiles unambiguous GoalSpec with user answers and custom notes', () => {
      const store = useClarificationGateStore.getState();
      store.openGate('做个用户管理页', 'auto');
      store.toggleOption('q_platform', 'desktop', false);
      store.setCustomNotes('支持离线模式');

      const spec = store.compileGoalSpec();
      expect(spec.isSkippedByUser).toBe(false);
      expect(spec.targetPlatform).toContain('Tauri');
      expect(spec.constraints.some((c) => c.includes('支持离线模式'))).toBe(true);
      expect(spec.compiledPrompt).toContain('[Goal Spec · 无歧义目标规格书]');
      expect(useClarificationGateStore.getState().isOpen).toBe(false);
    });
  });
});
