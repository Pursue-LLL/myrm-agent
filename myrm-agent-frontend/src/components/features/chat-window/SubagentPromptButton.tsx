'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/shared/useToast';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import { ArrowDown } from 'lucide-react';

/** 倒计时只作提示：到 0 后按钮仍在，直到被点击或新的回复到来。 */
const COUNTDOWN_SECONDS = 5;

/** 只在提示可见期间挂载，所以每次出现倒计时都从头开始。 */
const ViewResultsPrompt = () => {
  const t = useTranslations('chat');
  const [countdown, setCountdown] = useState(COUNTDOWN_SECONDS);

  const { setSubagentPromptVisible, clearSubagentPromptTimer, sendMessage } = useChatStore(
    useShallow((state) => ({
      setSubagentPromptVisible: state.setSubagentPromptVisible,
      clearSubagentPromptTimer: state.clearSubagentPromptTimer,
      sendMessage: state.sendMessage,
    })),
  );

  useEffect(() => {
    if (countdown === 0) {
      return;
    }
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const handleClick = async () => {
    setSubagentPromptVisible(false);
    clearSubagentPromptTimer();
    try {
      await sendMessage(t('subagent.viewResults'));
    } catch (error) {
      // sendMessage 在服务端仍在执行另一轮时会 reject；其余未发出的情况由 store 自行提示。
      console.warn('Subagent results request was not sent:', error);
      toast({ title: t('subagent.viewResultsFailed'), variant: 'destructive' });
    }
  };

  return (
    <div className="fixed bottom-24 left-1/2 transform -translate-x-1/2 z-50 animate-in fade-in-0 slide-in-from-bottom-4 duration-300">
      <Button
        onClick={handleClick}
        className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-full px-6 py-3"
      >
        <ArrowDown className="w-4 h-4" />
        <span>
          {t('subagent.viewResults')}
          {countdown > 0 && <span className="ml-1 opacity-70">({countdown}s)</span>}
        </span>
      </Button>
    </div>
  );
};

const SubagentPromptButton = () => {
  const visible = useChatStore((state) => state.subagentPromptVisible);
  return visible ? <ViewResultsPrompt /> : null;
};

export default SubagentPromptButton;
