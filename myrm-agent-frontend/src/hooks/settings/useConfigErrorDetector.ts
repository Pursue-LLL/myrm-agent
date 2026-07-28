'use client';
import { useEffect, useState } from 'react';
import useChatStore from '@/store/useChatStore';

export interface ConfigError {
  error_type: string;
  messages?: { en: string; zh: string };
  resolution_steps?: string[];
  config_url?: string;
}

/**
 * 监听聊天消息中的错误，自动检测后端返回的配置类错误
 */
export function useConfigErrorDetector() {
  const messages = useChatStore((state) => state.messages);
  const [configError, setConfigError] = useState<ConfigError | null>(null);

  useEffect(() => {
    if (messages.length === 0) return;

    const lastMessage = messages[messages.length - 1];

    if (lastMessage.role === 'assistant' && lastMessage.metadata) {
      const metadata = lastMessage.metadata as Record<string, unknown>;
      const errorType = metadata.error_type as string | undefined;

      if (errorType && typeof errorType === 'string') {
        setConfigError({
          error_type: errorType,
          messages: metadata.messages as { en: string; zh: string } | undefined,
          resolution_steps: metadata.resolution_steps as string[] | undefined,
          config_url: (metadata.config_url as string) || '/settings/models',
        });
      }
    }
  }, [messages]);

  const clearConfigError = () => setConfigError(null);

  return {
    configError,
    clearConfigError,
  };
}
