/**
 * [INPUT]
 * - ./messageInputHarness (POS: 输入区集成测试的共享替身)
 * - ../MessageInput (POS: 聊天输入区视图层)
 *
 * [OUTPUT]
 * Vitest: 输入区把各单元接到一起的回调：表单提交、历史弹窗的选择 / 悬停 / 关闭、@ 引用的选择、
 * 历史记录读取输入框当前内容与当前智能体、输入时只在历史弹窗打开着才去关闭它。
 *
 * [POS]
 * 与 MessageInput.keyboard.test.tsx 共用一套替身：每个用例只经由 DOM 事件与替身收到的属性来断言。
 */
import { fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  callStubProp,
  history,
  hookOf,
  installMessageInputHarness,
  mention,
  renderInput,
  setHook,
  stubProps,
} from './messageInputHarness';
import { expectNonNull } from '@/test-utils/expectDefined';
import type { AgentConfig } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

installMessageInputHarness();

describe('MessageInput wiring', () => {
  describe('the form', () => {
    it('sends on submit without letting the browser navigate', () => {
      const { container } = renderInput();
      const form = container.querySelector('form');
      expectNonNull(form, 'the composer form');

      const proceeded = fireEvent.submit(form);

      expect(proceeded).toBe(false);
      expect(hookOf().handleSubmit).toHaveBeenCalledTimes(1);
    });
  });

  describe('the history popup', () => {
    it('fills the input with the entry that was picked', () => {
      history().confirm.mockReturnValue('an earlier message');
      renderInput();

      callStubProp('InputHistoryPopup', 'onSelect', 2);

      expect(history().confirm).toHaveBeenCalledExactlyOnceWith(2);
      expect(hookOf().setInputMessage).toHaveBeenCalledExactlyOnceWith('an earlier message');
    });

    it('leaves the input alone when there is no entry to fill it with', () => {
      history().confirm.mockReturnValue(undefined);
      renderInput();

      callStubProp('InputHistoryPopup', 'onSelect', 2);

      expect(hookOf().setInputMessage).not.toHaveBeenCalled();
    });

    it('follows the pointer and closes from the popup', () => {
      renderInput();

      callStubProp('InputHistoryPopup', 'onHover', 3);
      callStubProp('InputHistoryPopup', 'onClose');

      expect(history().setActiveIndex).toHaveBeenCalledExactlyOnceWith(3);
      expect(history().close).toHaveBeenCalledTimes(1);
    });

    it('is not closed by typing while it is not open', () => {
      const { textarea } = renderInput();

      fireEvent.change(textarea, { target: { value: 'a' } });

      expect(hookOf().handleInputChange).toHaveBeenCalledTimes(1);
      expect(history().close).not.toHaveBeenCalled();
    });

    it('reads the current input and the current agent when it looks up entries', () => {
      setHook({ inputMessage: 'half-written' });
      useChatStore.setState({ agentConfig: { agentId: 'agent-7' } as AgentConfig });
      renderInput();

      const options = stubProps('useInputHistory');

      expect(options.agentId).toBe('agent-7');
      expect((options.getInputValue as () => string)()).toBe('half-written');
    });
  });

  describe('the @ mention popover', () => {
    it('hands the picked reference to the mention hook together with the input setter', () => {
      renderInput();
      const reference = { id: 'reference-1' };

      callStubProp('ReferenceMentionPopover', 'onSelect', reference);

      expect(mention().selectReference).toHaveBeenCalledExactlyOnceWith(reference, hookOf().setInputMessage);
    });
  });
});
