'use client';

import { useAppshotListener } from '@/hooks/tauri/useAppshotListener';
import { useInlineInputListener } from '@/hooks/tauri/useInlineInputListener';
import { useThemePackageOpenListener } from '@/hooks/tauri/useThemePackageOpenListener';

const AppshotInitializer = () => {
  useAppshotListener();
  useInlineInputListener();
  useThemePackageOpenListener();
  return null;
};

export default AppshotInitializer;
