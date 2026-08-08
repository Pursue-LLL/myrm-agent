'use client';

import { lazy, Suspense, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useSearchParams, useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import LibraryTabs, { type LibraryTab } from './components/LibraryTabs';
import MediaGallery from './components/MediaGallery';
import WikiGraphInsightsPanel from './components/WikiGraphInsightsPanel';

const WikiGraph3D = dynamic(() => import('./components/WikiGraph3D'), {
  ssr: false,
  loading: () => (
    <div className="flex min-h-[480px] items-center justify-center">
      <Loader2 className="size-6 animate-spin text-muted-foreground" />
    </div>
  ),
});

const SkillsSection = lazy(() => import('@/components/features/settings/sections/ai-tools/SkillsSection'));

const LoadingFallback = () => (
  <div className="flex items-center justify-center py-20">
    <Loader2 className="size-6 animate-spin text-muted-foreground" />
  </div>
);

const VALID_TABS = new Set<LibraryTab>(['gallery', 'skills', 'graph']);

function resolveLibraryTab(value: string | null): LibraryTab {
  if (value && VALID_TABS.has(value as LibraryTab)) {
    return value as LibraryTab;
  }
  return 'gallery';
}

const Page = () => {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialTab = resolveLibraryTab(searchParams.get('tab'));
  const [activeTab, setActiveTab] = useState<LibraryTab>(initialTab);
  const agentId = searchParams.get('agentId');

  useEffect(() => {
    setActiveTab(resolveLibraryTab(searchParams.get('tab')));
  }, [searchParams]);

  const handleTabChange = (tab: LibraryTab) => {
    setActiveTab(tab);
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', tab);
    router.replace(`/library?${params.toString()}`, { scroll: false });
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
      {activeTab === 'graph' && (
        <div className="flex flex-col gap-4 lg:flex-row">
          <div className="min-h-[480px] flex-1">
            <WikiGraph3D agentId={agentId} />
          </div>
          <WikiGraphInsightsPanel agentId={agentId} />
        </div>
      )}
    </div>
  );
};

export default Page;
