import React from 'react';
import ThinkBox from '@/components/features/markdown-render-tools/ThinkBox';
import { getChildrenAsText } from '@/lib/utils/reactUtils';

const ThinkTagProcessor = ({ children }: { children: React.ReactNode }) => {
  const value = getChildrenAsText(children);
  return <ThinkBox content={value} />;
};

export default ThinkTagProcessor;
