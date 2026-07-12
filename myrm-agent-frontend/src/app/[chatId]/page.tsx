import ChatWindowNew from '@/components/features/chat-window/ChatWindow';
import React from 'react';

export const prefetch = 'allow-runtime';

const Page = ({ params }: { params: Promise<{ chatId: string }> }) => {
  const { chatId } = React.use(params);
  return <ChatWindowNew id={chatId} />;
};

export default Page;
