'use client';

import { useAppshotListener } from '@/hooks/useAppshotListener';
import { useInlineInputListener } from '@/hooks/useInlineInputListener';

const AppshotInitializer = () => {
  useAppshotListener();
  useInlineInputListener();
  return null;
};

export default AppshotInitializer;
