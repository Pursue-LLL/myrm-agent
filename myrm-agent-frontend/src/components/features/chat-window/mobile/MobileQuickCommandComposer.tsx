'use client';

/**
 * [INPUT]
 * - react-textarea-autosize (POS: 随内容自增的多行输入)
 * - useDraftPersistence (POS: 以 chatId 隔离的草稿防抖持久化)
 * - useMobilePromptHistory (POS: 会话隔离的提示词历史漫游)
 * - SpeechInputButton (POS: 按住说话，转写先落草稿再由用户确认发送)
 * - extractKeyterms (POS: 领域热词，提升口述专有名词识别率)
 *
 * [OUTPUT]
 * - MobileQuickCommandComposer: 移动端指挥条输入区（辅助工具栏 + 多行输入 + 语音 + 发送）
 *
 * [POS]
 * 移动端指挥中心的输入面。职责边界严格限定为「接收与确认用户意图」：
 * 短指令原地直达，长文交接给完整会话页（见 MobileStatusBoard 的常驻「查看完整对话」）。
 * 因此不在此处提供全屏编辑器与模板体系，长文写作统一由主 Chat 的完整 composer 承担。
 * 回车沿用多行输入框的原生语义插入换行，提交只走常驻发送按钮。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Send } from 'lucide-react';
import TextareaAutosize from 'react-textarea-autosize';
import { useTranslations } from 'next-intl';

import { Button } from '@/components/primitives/button';
import SpeechInputButton from '@/components/features/message-input-actions/SpeechInputButton';
import { useDraftPersistence } from '@/hooks/shared/useDraftPersistence';
import { extractKeyterms } from '../speechKeyterms';
import { MobileQuickControlAccessoryToolbar } from './MobileQuickControlAccessoryToolbar';
import { useMobilePromptHistory } from './useMobilePromptHistory';

/** 单行态与多行态的高度上限：既允许粘贴多行参考资料，又不挤压上方审批区。 */
const MIN_ROWS = 1;
const MAX_ROWS = 4;

/** `/ask`、`/side` 走旁路问答面板，其余内容一律作为普通指令下发。 */
const ADVISOR_COMMAND_PATTERN = /^\/(?:ask|side)(?:[ \t]+([\s\S]*))?$/i;

export interface MobileQuickCommandComposerProps {
  chatId: string;
  /** 运行中：提交语义为 steer 纠偏，空闲时为新指令。 */
  loading: boolean;
  messages: { content: string; role: string }[];
  onSubmit: (text: string) => void;
  onOpenAdvisor: (question: string) => void;
}

export function MobileQuickCommandComposer({
  chatId,
  loading,
  messages,
  onSubmit,
  onOpenAdvisor,
}: MobileQuickCommandComposerProps) {
  const t = useTranslations('agent.mobileCommand');

  const [draft, setDraft] = useState('');
  /** 历史漫游期间展示的文本；始终不写入草稿存储，避免历史覆盖用户真实草稿。 */
  const [browsedText, setBrowsedText] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { historyCount, currentIndex, pushHistory, navigatePrevious, resetNavigation } = useMobilePromptHistory(chatId);

  // 只喂真实草稿：历史漫游展示值不参与持久化，从根上避免「回溯一次即丢草稿」。
  const { initialDraft, clearDraft } = useDraftPersistence(chatId, draft);

  const isBrowsingHistory = currentIndex >= 0;
  const value = isBrowsingHistory ? (browsedText ?? '') : draft;
  const keyterms = useMemo(() => extractKeyterms(messages), [messages]);

  const focusInput = useCallback(() => {
    inputRef.current?.focus();
  }, []);

  const exitHistoryBrowsing = useCallback(() => {
    resetNavigation();
    setBrowsedText(null);
  }, [resetNavigation]);

  // 草稿随 chatId 整体替换：切到无草稿的会话时必须显式清空，
  // 否则上一会话的草稿会残留在输入框并被写入新会话的存储键。
  useEffect(() => {
    setDraft(initialDraft ?? '');
    exitHistoryBrowsing();
  }, [chatId, initialDraft, exitHistoryBrowsing]);

  const commit = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        return;
      }
      const advisorMatch = trimmed.match(ADVISOR_COMMAND_PATTERN);
      if (advisorMatch) {
        clearDraft();
        setDraft('');
        exitHistoryBrowsing();
        onOpenAdvisor(advisorMatch[1]?.trim() ?? '');
        return;
      }
      pushHistory(trimmed);
      clearDraft();
      setDraft('');
      exitHistoryBrowsing();
      onSubmit(trimmed);
    },
    [clearDraft, exitHistoryBrowsing, onOpenAdvisor, onSubmit, pushHistory],
  );

  /**
   * 语音转写先追加进草稿、由用户确认后再下发。
   * 流式转写会把长句切成多个 final 段，逐段直发会打断运行中的任务，
   * 因此这里只做追加（interim 预览由 SpeechInputButton 自带）。
   */
  const handleTranscript = useCallback(
    (text: string) => {
      const transcript = text.trim();
      if (!transcript) {
        return;
      }
      exitHistoryBrowsing();
      setDraft((prev) => (prev.trim() ? `${prev.replace(/\s+$/, '')} ${transcript}` : transcript));
      focusInput();
    },
    [exitHistoryBrowsing, focusInput],
  );

  /**
   * 历史按钮：未漫游时回到最近一条历史，已停在最旧一条则交还用户草稿。
   * 草稿本身由 draft 状态与草稿持久化承担，回溯过程不触碰它。
   */
  const handleHistoryStep = useCallback(() => {
    if (currentIndex === 0) {
      exitHistoryBrowsing();
      return;
    }
    setBrowsedText(navigatePrevious());
  }, [currentIndex, exitHistoryBrowsing, navigatePrevious]);

  const handleChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      if (isBrowsingHistory) {
        exitHistoryBrowsing();
      }
      setDraft(event.target.value);
    },
    [exitHistoryBrowsing, isBrowsingHistory],
  );

  const handlePasteText = useCallback(
    (text: string) => {
      exitHistoryBrowsing();
      setDraft((prev) => (prev && !/\s$/.test(prev) ? `${prev} ${text}` : `${prev}${text}`));
      focusInput();
    },
    [exitHistoryBrowsing, focusInput],
  );

  const handleClear = useCallback(() => {
    if (draft.trim().length > 3) {
      pushHistory(draft.trim());
    }
    clearDraft();
    setDraft('');
    exitHistoryBrowsing();
    focusInput();
  }, [clearDraft, draft, exitHistoryBrowsing, focusInput, pushHistory]);

  return (
    <>
      <MobileQuickControlAccessoryToolbar
        historyCount={historyCount}
        historyCurrentIndex={currentIndex}
        currentValue={value}
        onNavigateHistory={() => {
          handleHistoryStep();
          focusInput();
        }}
        onRequestFocusInput={focusInput}
        onPasteText={handlePasteText}
        onOpenAdvisor={() => onOpenAdvisor('')}
        onClearInput={handleClear}
      />
      <div className="flex items-end gap-2 p-3 pt-1.5">
        {/* 录音时按钮旁展开转写预览：气泡自带固定像素上限，窄屏下会撑破 max-w 横穿进输入区，
            故用 overflow 裁剪，保证输入区始终保有可用宽度。 */}
        <div className="flex min-w-0 max-w-[45%] shrink items-end overflow-hidden">
          <SpeechInputButton mode="push-to-talk" onTranscript={handleTranscript} keyterms={keyterms} />
        </div>
        <TextareaAutosize
          ref={inputRef}
          value={value}
          onChange={handleChange}
          minRows={MIN_ROWS}
          maxRows={MAX_ROWS}
          aria-label={t('quickCommandInputLabel')}
          placeholder={loading ? t('steerPlaceholder') : t('quickCommandPlaceholder')}
          className="min-w-0 flex-1 resize-none rounded-xl border bg-secondary/50 px-3 py-2 text-sm leading-relaxed outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
        />
        <Button
          size="icon"
          className="h-10 w-10 shrink-0 rounded-xl"
          onClick={() => commit(value)}
          disabled={!value.trim()}
          aria-label={t('send')}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </>
  );
}
