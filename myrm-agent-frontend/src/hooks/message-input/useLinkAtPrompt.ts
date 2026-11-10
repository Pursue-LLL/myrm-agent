/**
 * [INPUT]
 * - 输入框文本、写回文本的函数与输入框 ref
 *
 * [OUTPUT]
 * - useLinkAtPrompt: 输入里出现没加 @ 的链接时询问是否补上 @（让 Agent 读取该链接）；同一条消息只问一次，「不再提醒」记在 localStorage
 *
 * [POS]
 * 聊天输入业务 Hook 的链接提示部分：只管提示的开合、答复与 @ 的写回，不碰消息提交。
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

const LINK_PATTERN = /(^|[^@])(https?:\/\/[^\s]+)/;
const DONT_REMIND_STORAGE_KEY = 'dontRemindLinkDialog';

interface DetectedLink {
  text: string;
  /** 链接在输入框文本里的起始位置（@ 要插入的位置）。 */
  position: number;
}

interface LinkAtPromptOptions {
  inputMessage: string;
  setInputMessage: (value: string) => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
}

function readDontRemindAgain(): boolean {
  return typeof window !== 'undefined' && localStorage.getItem(DONT_REMIND_STORAGE_KEY) === 'true';
}

export function useLinkAtPrompt({ inputMessage, setInputMessage, inputRef }: LinkAtPromptOptions) {
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const [dontRemindAgain, setDontRemindAgain] = useState(readDontRemindAgain);
  const detectedLinkRef = useRef<DetectedLink | null>(null);
  // 一条消息只问一次：答「否」之后继续编辑同一条消息不再追问；消息里不再有链接（发送、清空、删掉）才重新计。
  const askedRef = useRef(false);

  useEffect(() => {
    if (!LINK_PATTERN.test(inputMessage)) {
      askedRef.current = false;
    }
  }, [inputMessage]);

  const detectLink = useCallback(
    (text: string) => {
      const match = LINK_PATTERN.exec(text);
      if (!match || dontRemindAgain || askedRef.current) {
        return;
      }
      askedRef.current = true;
      detectedLinkRef.current = { text: match[2], position: match.index + match[1].length };
      setShowLinkDialog(true);
    },
    [dontRemindAgain],
  );

  // 勾选「不再提醒」后无论怎么答（含关闭对话框）都记下。
  const closeDialog = useCallback(() => {
    if (dontRemindAgain) {
      localStorage.setItem(DONT_REMIND_STORAGE_KEY, 'true');
    }
    detectedLinkRef.current = null;
    setShowLinkDialog(false);
  }, [dontRemindAgain]);

  const handleAddAtSymbol = useCallback(() => {
    const link = detectedLinkRef.current;
    if (link) {
      const { text, position } = link;
      setInputMessage(`${inputMessage.substring(0, position)}@${inputMessage.substring(position)}`);

      setTimeout(() => {
        const input = inputRef.current;
        if (input) {
          const caret = position + text.length + 1;
          input.selectionStart = caret;
          input.selectionEnd = caret;
          input.focus();
        }
      }, 0);
    }
    closeDialog();
  }, [closeDialog, inputMessage, inputRef, setInputMessage]);

  return {
    showLinkDialog,
    dontRemindAgain,
    setDontRemindAgain,
    detectLink,
    handleAddAtSymbol,
    handleSkipAtSymbol: closeDialog,
  };
}
