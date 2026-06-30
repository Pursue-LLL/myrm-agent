'use client';

import { ArrowLeft } from 'lucide-react';
import { useTranslations } from 'next-intl';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { use, useCallback } from 'react';

const CanvasWorkspace = dynamic(
  () => import('@/components/features/canvas/CanvasWorkspace'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-screen text-muted-foreground">
        Loading...
      </div>
    ),
  },
);

export default function CanvasEditorPage({ params }: { params: Promise<{ canvasId: string }> }) {
  const { canvasId } = use(params);
  const t = useTranslations('canvas');
  const router = useRouter();

  const handleBack = useCallback(() => {
    router.push('/canvas');
  }, [router]);

  return (
    <div className="relative w-screen h-screen">
      <button
        onClick={handleBack}
        className="absolute top-3 left-3 z-[999] flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-background/80 backdrop-blur-sm border border-border text-sm text-foreground hover:bg-accent transition-colors shadow-sm"
      >
        <ArrowLeft size={16} />
        <span className="hidden sm:inline">{t('back')}</span>
      </button>
      <CanvasWorkspace canvasId={canvasId} />
    </div>
  );
}
