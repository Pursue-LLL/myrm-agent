import { describe, it, expect, beforeEach } from 'vitest';
import { usePlaybookInspectorStore } from '../usePlaybookInspectorStore';

describe('usePlaybookInspectorStore', () => {
  beforeEach(() => {
    usePlaybookInspectorStore.getState().reset();
  });

  it('loads initial default rules correctly with 3 different lifecycle statuses', () => {
    const rules = Object.values(usePlaybookInspectorStore.getState().rules);
    expect(rules).toHaveLength(3);
    expect(rules.find((r) => r.status === 'active')).toBeDefined();
    expect(rules.find((r) => r.status === 'degraded')).toBeDefined();
    expect(rules.find((r) => r.status === 'retired')).toBeDefined();
  });

  it('revives degraded or retired rule and restores status to active', () => {
    usePlaybookInspectorStore.getState().reviveRule('pb-file-line-limit');
    const revived = usePlaybookInspectorStore.getState().rules['pb-file-line-limit'];
    expect(revived.status).toBe('active');
    expect(revived.winRate).toBeGreaterThanOrEqual(0.8);
  });

  it('toggles pin state to prevent rule retirement', () => {
    const initialPin = usePlaybookInspectorStore.getState().rules['pb-file-line-limit'].isPinned;
    usePlaybookInspectorStore.getState().togglePinRule('pb-file-line-limit');
    expect(usePlaybookInspectorStore.getState().rules['pb-file-line-limit'].isPinned).toBe(!initialPin);
  });

  it('retires active rule', () => {
    usePlaybookInspectorStore.getState().retireRule('pb-strict-typing');
    const retired = usePlaybookInspectorStore.getState().rules['pb-strict-typing'];
    expect(retired.status).toBe('retired');
    expect(retired.isPinned).toBe(false);
  });

  it('updates rule directive and title in place', () => {
    usePlaybookInspectorStore.getState().updateRule('pb-strict-typing', {
      title: '全面禁用 any 与 ts-ignore',
    });
    const updated = usePlaybookInspectorStore.getState().rules['pb-strict-typing'];
    expect(updated.title).toBe('全面禁用 any 与 ts-ignore');
  });

  it('adds custom rule and sets initial active state', () => {
    const rule = usePlaybookInspectorStore.getState().addRule({
      title: 'UI 必须支持无障碍 aria-label',
      triggerCondition: '编写 JSX 按钮或可交互标签时',
      directive: '必须提供清晰语义化 aria-label 与原生语义标签',
    });
    expect(rule.id).toBeDefined();
    expect(rule.status).toBe('active');
    expect(rule.isPinned).toBe(true);
    expect(usePlaybookInspectorStore.getState().rules[rule.id]).toBeDefined();
  });
});
