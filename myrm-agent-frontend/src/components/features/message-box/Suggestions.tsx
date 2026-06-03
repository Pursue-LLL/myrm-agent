import React from 'react';
import { Layers3, Plus } from 'lucide-react';
import useChatStore, { Message } from '@/store/useChatStore';
import { useTranslations } from 'next-intl';

const Suggestions = React.memo(({ message, loading }: { message: Message; loading: boolean }) => {
  const sendMessage = useChatStore((state) => state.sendMessage);
  const t = useTranslations('chat');

  return (
    message.suggestions &&
    message.suggestions.length > 0 &&
    message.role === 'assistant' &&
    !loading && (
      <>
        <div className="h-px w-full bg-secondary" />
        <div className="flex flex-col space-y-3 text-black dark:text-white">
          <div className="flex flex-row items-center space-x-2 mt-4">
            <Layers3 />
            <h3 className="text-xl font-medium">{t('related')}</h3>
          </div>
          <div className="flex flex-col space-y-3">
            {message.suggestions.map((suggestion, i) => (
              <div className="flex flex-col space-y-3 text-sm" key={i}>
                <div className="h-px w-full bg-secondary" />
                <div
                  onClick={() => {
                    sendMessage(suggestion, undefined);
                  }}
                  className="cursor-pointer flex flex-row justify-between font-medium space-x-2 items-center"
                >
                  <p className="transition duration-200 hover:text-primary">{suggestion}</p>
                  <Plus size={20} className="text-primary flex-shrink-0" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </>
    )
  );
});

Suggestions.displayName = 'Suggestions';

export default Suggestions;
