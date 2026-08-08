'use client';

/**
 * Root-level localhost E2E bridge — mounts outside LocalizedProviders Suspense so
 * CDP Chrome E2E can reach attachToChat when Turbopack/RSC is slow under parallel load.
 */
import E2EChatBridge from '@/components/dev/E2EChatBridge';
import E2EWikiBridge from '@/components/dev/E2EWikiBridge';

function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}

export default function E2eBridgeLoader() {
  if (!isLocalDevHost()) {
    return null;
  }
  return (
    <>
      <E2EChatBridge />
      <E2EWikiBridge />
    </>
  );
}
