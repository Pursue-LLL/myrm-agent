'use client';

import ChatWindowNew from '@/components/features/chat-window/ChatWindow';
import { useParams } from 'next/navigation';

const Page = () => {
  const params = useParams();
  const chatId = typeof params.chatId === 'string' ? params.chatId : undefined;
  return <ChatWindowNew id={chatId} />;
};

export default Page;
