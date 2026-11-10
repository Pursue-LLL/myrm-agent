import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import { toast } from '@/hooks/shared/useToast';
import { getApiUrl } from '@/lib/api';
import { riskHeldErrorFromResponse } from '@/services/riskHeldToast';

import type { InstructionPanelProps } from './InstructionPanel';

interface InstructionAssistOptions {
  /** 只有指令卡片需要这两项能力。 */
  active: boolean;
  /** 已保存智能体的 id；没有时不读取历史。 */
  agentId?: string;
  prompt: string;
  setPrompt: (value: string | ((previous: string) => string)) => void;
}

/**
 * 指令卡片的服务端能力：把模型流式生成的提示词写进草稿，并读取已保存智能体的提示词版本历史。
 * 生成失败一律提示用户；文本被风控规则拦下时已有专门的提示，不再重复。
 */
export function useInstructionAssist({ active, agentId, prompt, setPrompt }: InstructionAssistOptions) {
  const t = useTranslations('agent.configEditor');
  const [isGeneratingAi, setIsGeneratingAi] = useState(false);
  const [history, setHistory] = useState<InstructionPanelProps['history']>([]);

  useEffect(() => {
    if (!active || !agentId) {
      return;
    }
    fetch(getApiUrl(`/user-agents/${agentId}/history`))
      .then((res) => res.json())
      .then((data) => {
        if (data.data) {
          setHistory(data.data);
        }
      })
      .catch((err) => console.error('Failed to fetch history:', err));
  }, [active, agentId]);

  const handleAiGenerate = useCallback(
    async (intent: string) => {
      if (!intent.trim()) {
        return;
      }
      setIsGeneratingAi(true);
      try {
        const response = await fetch(getApiUrl('/user-agents/generate-prompt'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intent, locale: navigator.language || 'en-US', current_prompt: prompt }),
        });
        if (!response.ok) {
          if (await riskHeldErrorFromResponse(response)) {
            return;
          }
          if (response.status === 422) {
            const errorData = await response.json();
            toast({
              title: t('aiGenerateConfigMissing'),
              description: typeof errorData.detail === 'string' ? errorData.detail : undefined,
              variant: 'destructive',
            });
            return;
          }
          throw new Error('Failed to generate prompt');
        }
        if (!response.body) {
          throw new Error('No response body');
        }
        let isFirstChunk = true;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'content' && data.data) {
                  if (isFirstChunk) {
                    setPrompt('');
                    isFirstChunk = false;
                  }
                  setPrompt((prev) => prev + data.data);
                } else if (data.type === 'error') {
                  toast({
                    title: t('aiGenerateFailed'),
                    description: typeof data.error === 'string' ? data.error : undefined,
                    variant: 'destructive',
                  });
                }
              } catch (e) {
                console.error('Failed to parse SSE chunk', e);
              }
            }
          }
        }
      } catch (error) {
        console.error('Failed to generate AI prompt:', error);
        toast({ title: t('aiGenerateFailed'), variant: 'destructive' });
      } finally {
        setIsGeneratingAi(false);
      }
    },
    [prompt, setPrompt, t],
  );

  return { isGeneratingAi, history, handleAiGenerate };
}
