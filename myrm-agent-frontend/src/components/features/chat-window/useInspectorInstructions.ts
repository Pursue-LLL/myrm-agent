/**
 * [INPUT]
 * - @/store/useChatStore::sendMessage (POS: 把指令作为用户消息发出)
 * - next-intl chat.inspector (POS: 元素指令的本地化模板)
 *
 * [OUTPUT]
 * - useInspectorInstructions: 浏览器 / 桌面检查器「发给 Agent」回调，指令带 `[Browser Inspector]` / `[Desktop Inspector]` 前缀
 *
 * [POS]
 * ChatWindow 的检查器层。选中了元素（refId）时套用元素模板，没有填指令则回落到默认指令；
 * 没有 refId 时原样发出用户输入。
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';

export type InspectorInstructionHandler = (instruction: string, refId: string | null) => void;

export interface InspectorInstructions {
  handleInspectorInstruction: InspectorInstructionHandler;
  handleDesktopInspectorInstruction: InspectorInstructionHandler;
}

export function useInspectorInstructions(): InspectorInstructions {
  const inspectorT = useTranslations('chat.inspector');
  const sendMessage = useChatStore((s) => s.sendMessage);

  const handleInspectorInstruction = useCallback<InspectorInstructionHandler>(
    (instruction, refId) => {
      const formattedInstruction = refId
        ? `[Browser Inspector] ${inspectorT('browserElementPrompt', {
            refId,
            instruction: instruction || inspectorT('defaultInstruction'),
          })}`
        : `[Browser Inspector] ${instruction}`;
      sendMessage(formattedInstruction);
    },
    [inspectorT, sendMessage],
  );

  const handleDesktopInspectorInstruction = useCallback<InspectorInstructionHandler>(
    (instruction, refId) => {
      const formattedInstruction = refId
        ? `[Desktop Inspector] ${inspectorT('desktopElementPrompt', {
            refId,
            instruction: instruction || inspectorT('defaultInstruction'),
          })}`
        : `[Desktop Inspector] ${instruction}`;
      sendMessage(formattedInstruction);
    },
    [inspectorT, sendMessage],
  );

  return { handleInspectorInstruction, handleDesktopInspectorInstruction };
}
