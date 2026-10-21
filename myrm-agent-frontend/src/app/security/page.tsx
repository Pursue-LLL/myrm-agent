'use client';

import { Suspense } from 'react';
import SecurityDashboard from '@/components/security/SecurityDashboard';

const SecurityLoading = () => (
  <div className="flex items-center justify-center min-h-[50vh]">
    <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
  </div>
);

const Page = () => {
  return (
    <div className="container mx-auto py-8 px-4">
      <Suspense fallback={<SecurityLoading />}>
        <SecurityDashboard />
      </Suspense>
    </div>
  );
};

export default Page;
