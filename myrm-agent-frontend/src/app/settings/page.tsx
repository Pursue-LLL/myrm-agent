'use client';

import { Suspense } from 'react';
import SettingsLayout from '@/components/ui/settings/SettingsLayout';

const SettingsLoading = () => (
  <div className="flex items-center justify-center min-h-[50vh]">
    <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
  </div>
);

const Page = () => {
  return (
    <Suspense fallback={<SettingsLoading />}>
      <SettingsLayout />
    </Suspense>
  );
};

export default Page;
