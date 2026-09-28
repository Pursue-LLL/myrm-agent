import { describe, expect, it, vi } from 'vitest';
import { resolveDualChannelAction, type DualChannelKeyEvent } from '../messageInputKeyRouter';

function createMockKeyEvent(overrides: Partial<DualChannelKeyEvent> = {}): DualChannelKeyEvent {
  return {
    key: 'Enter',
    altKey: false,
    shiftKey: false,
    preventDefault: vi.fn(),
    ...overrides,
  };
}

describe('resolveDualChannelAction (Dual-Channel Steering vs Queue Router)', () => {
  describe('loading=true (Agent 运行时)', () => {
    it('Alt+Enter 应阻止默认行为并路由至 queue 通道（非中断排队跟进）', () => {
      const event = createMockKeyEvent({ altKey: true, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: true });

      expect(action).toBe('queue');
      expect(event.preventDefault).toHaveBeenCalledTimes(1);
    });

    it('普通 Enter 应阻止默认行为并路由至 submit 通道（触发 steering/redirect 引导纠偏）', () => {
      const event = createMockKeyEvent({ altKey: false, shiftKey: false, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: true });

      expect(action).toBe('submit');
      expect(event.preventDefault).toHaveBeenCalledTimes(1);
    });

    it('Shift+Enter 应保持原生换行（返回 none，不阻止默认行为）', () => {
      const event = createMockKeyEvent({ shiftKey: true, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: true });

      expect(action).toBe('none');
      expect(event.preventDefault).not.toHaveBeenCalled();
    });
  });

  describe('loading=false (Agent 空闲态)', () => {
    it('普通 Enter 应阻止默认行为并正常触发 submit', () => {
      const event = createMockKeyEvent({ altKey: false, shiftKey: false, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: false });

      expect(action).toBe('submit');
      expect(event.preventDefault).toHaveBeenCalledTimes(1);
    });

    it('Alt+Enter 在空闲时也应正常触发 submit（无需排队）', () => {
      const event = createMockKeyEvent({ altKey: true, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: false });

      expect(action).toBe('submit');
      expect(event.preventDefault).toHaveBeenCalledTimes(1);
    });

    it('Shift+Enter 在空闲时保持原生换行', () => {
      const event = createMockKeyEvent({ shiftKey: true, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: false });

      expect(action).toBe('none');
      expect(event.preventDefault).not.toHaveBeenCalled();
    });
  });

  describe('IME 输入法组合态保护 (isComposing)', () => {
    it('isComposing=true 时按下 Enter 不应触发任何动作或阻止事件（确保拼音候选词正常上屏）', () => {
      const event = createMockKeyEvent({ isComposing: true, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: true });

      expect(action).toBe('none');
      expect(event.preventDefault).not.toHaveBeenCalled();
    });

    it('key="Process" 属于 W3C IME 判定，不应触发动作', () => {
      const event = createMockKeyEvent({ key: 'Process' });
      const action = resolveDualChannelAction(event, { loading: true });

      expect(action).toBe('none');
      expect(event.preventDefault).not.toHaveBeenCalled();
    });

    it('keyCode=229 属于 Windows IME 判定，不应触发动作', () => {
      const event = createMockKeyEvent({ keyCode: 229, key: 'Enter' });
      const action = resolveDualChannelAction(event, { loading: true });

      expect(action).toBe('none');
      expect(event.preventDefault).not.toHaveBeenCalled();
    });
  });

  describe('其他按键事件放行', () => {
    it('普通文本按键（如字符 a、Backspace、Tab）不应被拦截', () => {
      const event = createMockKeyEvent({ key: 'a' });
      const action = resolveDualChannelAction(event, { loading: true });

      expect(action).toBe('none');
      expect(event.preventDefault).not.toHaveBeenCalled();
    });
  });
});
