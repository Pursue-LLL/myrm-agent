/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 输入框草稿)
 *
 * [OUTPUT]
 * - prefillComposerWithUseCase: 召唤专家后把模板的示例场景预填进输入框，但绝不覆盖用户已输入的内容
 *
 * [POS]
 * FeaturedExpertChips 与 ExpertSummonPopover 共用。召唤会跳转到该专家的新会话，输入框草稿是全局状态，
 * 直接覆盖会让用户刚写的内容在一次点击后消失。
 */

import useChatStore from '@/store/useChatStore';

export function prefillComposerWithUseCase(useCase: string | undefined): void {
  if (!useCase) {
    return;
  }
  const { inputMessage, setInputMessage } = useChatStore.getState();
  if (inputMessage.trim()) {
    return;
  }
  setInputMessage(useCase);
}
