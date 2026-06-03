'use client';

import { useAppshotListener } from '@/hooks/useAppshotListener';

const AppshotInitializer = () => {
  useAppshotListener();
  return null;
};

export default AppshotInitializer;
