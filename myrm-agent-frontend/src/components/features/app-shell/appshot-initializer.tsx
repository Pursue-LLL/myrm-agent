'use client';

import { useAppshotListener } from '@/hooks/tauri/useAppshotListener';
import { useInlineInputListener } from '@/hooks/tauri/useInlineInputListener';

const AppshotInitializer = () => {
  useAppshotListener();
  useInlineInputListener();
  return null;
};

export default AppshotInitializer;
