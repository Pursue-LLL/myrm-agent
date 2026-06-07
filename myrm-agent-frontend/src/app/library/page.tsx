'use client';

import { lazy, Suspense, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import LibraryTabs, { type LibraryTab } from './components/LibraryTabs';
import MediaGallery from './components/MediaGallery';
import WikiGraph3D from './components/WikiGraph3D';

const SkillsSection = lazy(() => import('@/components/features/settings/sections/ai-tools/SkillsSection'));

const LoadingFallback = () => (
  <div className="flex items-center justify-center py-20">
    <Loader2 className="size-6 animate-spin text-muted-foreground" />
  </div>
);

const Page = () => {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialTab = (searchParams.get('tab') as LibraryTab) || 'gallery';
  const [activeTab, setActiveTab] = useState<LibraryTab>(initialTab);

  const handleTabChange = (tab: LibraryTab) => {
    setActiveTab(tab);
    router.replace(`/library?tab=${tab}`, { scroll: false });
  };

  return (
    <div className="h-full py-4 px-4 md:px-6">
      <LibraryTabs activeTab={activeTab} onTabChange={handleTabChange} />
      {activeTab === 'gallery' && <MediaGallery />}
      {activeTab === 'skills' && (
        <Suspense fallback={<LoadingFallback />}>
          <SkillsSection />
        </Suspense>
      )}
      {activeTab === 'graph' && <WikiGraph3D />}
    </div>
  );
};

export default Page;
