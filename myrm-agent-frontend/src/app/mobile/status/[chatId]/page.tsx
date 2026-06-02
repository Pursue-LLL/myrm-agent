import MobileStatusBoard from '@/components/ui/chat-window/MobileStatusBoard';
import React from 'react';

const Page = ({ params }: { params: Promise<{ chatId: string }> }) => {
  const { chatId } = React.use(params);
  return <MobileStatusBoard chatId={chatId} />;
};

export default Page;
