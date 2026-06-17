import MobileSessionHub from '@/components/features/mobile/MobileSessionHub';
import { Suspense } from 'react';

export default function MobileHubPage() {
  return (
    <Suspense fallback={null}>
      <MobileSessionHub />
    </Suspense>
  );
}
