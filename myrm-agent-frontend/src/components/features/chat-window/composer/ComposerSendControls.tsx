'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线，待激活技能)
 * - @/store/chat/serverTurn::selectChatGenerating (POS: 服务端是否正在跑本会话的一轮)
 * - @/hooks/chat/useTurnStoppable::useTurnStoppable (POS: 当前聊天是否有 Stop 能够到达的回合)
 *
 * [OUTPUT]
 * - ComposerSendControls: 输入区右下角的发送、停止、纠偏、引导与排队按钮。
 *
 * [POS]
 * 按「是否在跑」与「有没有可发的内容」决定显示哪几个按钮：空闲时是发送（没有文字、附件、待激活技能时禁用）；
 * 运行中有内容可发时是纠偏 / 引导 / 排队三件加停止，没有内容时只有停止。服务端自己发起的一轮（后台工作唤醒）
 * 不带 `loading`，空闲分支仍要能 Stop 到它。
 */
import { ArrowRight, CornerDownLeft, ListPlus, Navigation, Square } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { useTurnStoppable } from '@/hooks/chat/useTurnStoppable';
import { selectChatGenerating } from '@/store/chat/serverTurn';
import useChatStore from '@/store/useChatStore';

interface ComposerSendControlsProps {
  loading: boolean;
  inputMessage: string;
  hasFiles: boolean;
  onStop: () => void;
  onRedirect: () => void | Promise<void>;
  onSteer: () => void | Promise<void>;
  onQueue: () => void | Promise<void>;
  onSend: () => void | Promise<void>;
}

export function ComposerSendControls({
  loading,
  inputMessage,
  hasFiles,
  onStop,
  onRedirect,
  onSteer,
  onQueue,
  onSend,
}: ComposerSendControlsProps) {
  const commonT = useTranslations('common');
  const chatT = useTranslations('chat');
  const serverTurnActive = useChatStore(selectChatGenerating);
  const turnStoppable = useTurnStoppable();
  const hasPendingSkill = useChatStore((s) => Boolean(s.pendingExplicitSkillActivation));
  const hasText = inputMessage.trim().length > 0;

  const stopButton = (
    <button
      type="button"
      onClick={onStop}
      // While the chat's history loads nothing is attached yet: Stop stays in place but cannot be pressed.
      disabled={!turnStoppable}
      className="bg-slate-500 dark:bg-white text-white dark:text-black hover:bg-black/80 dark:hover:bg-white/80 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-slate-500 dark:disabled:hover:bg-white transition duration-100 rounded-full p-2"
      aria-label={chatT('input.stop')}
    >
      <Square size={17} />
    </button>
  );

  if (loading) {
    return (
      <div className="flex items-center gap-1">
        {hasText || hasPendingSkill ? (
          <>
            <button
              type="button"
              onClick={() => void onRedirect()}
              className="bg-primary text-primary-foreground hover:bg-primary/80 transition duration-100 rounded-full p-2"
              aria-label={chatT('redirect.send')}
              title={chatT('redirect.tooltip')}
            >
              <CornerDownLeft size={17} />
            </button>
            <button
              type="button"
              onClick={() => void onSteer()}
              className="bg-muted-foreground/20 text-foreground hover:bg-muted-foreground/30 transition duration-100 rounded-full p-2"
              aria-label={chatT('steer.send')}
              title={chatT('steer.tooltip')}
            >
              <Navigation size={17} />
            </button>
            <button
              type="button"
              onClick={() => void onQueue()}
              className="bg-accent/60 text-white hover:bg-accent/80 transition duration-100 rounded-full p-2"
              aria-label={chatT('queue.sendLater')}
              title={chatT('queue.sendLaterTooltip')}
            >
              <ListPlus size={17} />
            </button>
          </>
        ) : null}
        {stopButton}
      </div>
    );
  }

  return (
    <>
      {serverTurnActive && stopButton}
      <span className="brand-elevation-slot">
        <button
          type="button"
          onClick={() => void onSend()}
          disabled={!hasText && !hasFiles && !hasPendingSkill}
          className="message-send-btn btn-brand-elevation bg-primary text-primary-foreground disabled:text-black/50 dark:disabled:text-white/50 disabled:bg-muted dark:disabled:bg-muted/30 hover:bg-primary-hover rounded-full p-2"
          aria-label={commonT('send')}
        >
          <ArrowRight size={17} />
        </button>
      </span>
    </>
  );
}
