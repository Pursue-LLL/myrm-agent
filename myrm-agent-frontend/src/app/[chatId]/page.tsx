import ChatWindowNew from '@/components/ui/chat-window/ChatWindow';
import React from 'react';

const Page = ({ params }: { params: Promise<{ chatId: string }> }) => {
  const { chatId } = React.use(params);
  return <ChatWindowNew id={chatId} />;
};

export default Page;
