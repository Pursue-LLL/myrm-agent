import React from 'react';

import MobileTakeoverBoard from '@/components/features/mobile/MobileTakeoverBoard';

/**
 * [INPUT]
 * - MobileTakeoverBoard (POS: 移动端 takeover 接管面板)
 *
 * [OUTPUT]
 * - /mobile/takeover/[chatId] route page
 *
 * [POS]
 * - 为签名接管链接提供页面路由壳层，将 chatId 透传到 MobileTakeoverBoard。
 */
const Page = ({ params }: { params: Promise<{ chatId: string }> }) => {
  const { chatId } = React.use(params);
  return <MobileTakeoverBoard chatId={chatId} />;
};

export default Page;
