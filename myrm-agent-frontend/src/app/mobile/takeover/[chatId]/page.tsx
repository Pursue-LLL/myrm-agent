import React from 'react';

import MobileTakeoverBoard from '@/components/features/mobile/MobileTakeoverBoard';

const Page = ({ params }: { params: Promise<{ chatId: string }> }) => {
  const { chatId } = React.use(params);
  return <MobileTakeoverBoard chatId={chatId} />;
};

export default Page;
