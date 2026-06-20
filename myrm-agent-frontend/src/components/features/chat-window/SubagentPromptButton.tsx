'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import { ArrowDown } from 'lucide-react';

const SubagentPromptButton = () => {
  const t = useTranslations('chat');
  const [countdown, setCountdown] = useState(5);

  const { subagentPromptVisible, setSubagentPromptVisible, clearSubagentPromptTimer, sendMessage } = useChatStore(
    useShallow((state) => ({
      subagentPromptVisible: state.subagentPromptVisible,
      setSubagentPromptVisible: state.setSubagentPromptVisible,
      clearSubagentPromptTimer: state.clearSubagentPromptTimer,
      sendMessage: state.sendMessage,
    })),
  );

  useEffect(() => {
    if (!subagentPromptVisible) {
      setCountdown(5);
      return;
    }

    const interval = setInterval(() => {
      setCountdown((prev) => Math.max(0, prev - 1));
    }, 1000);

    return () => clearInterval(interval);
  }, [subagentPromptVisible]);

  const handleClick = async () => {
    setSubagentPromptVisible(false);
    clearSubagentPromptTimer();
    await sendMessage('查看结果');
  };

  if (!subagentPromptVisible) return null;

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

export default SubagentPromptButton;
