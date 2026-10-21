'use client';

import { useEffect, useState, type ReactNode } from 'react';

interface DeferredMountProps {
  children: ReactNode;
  fallback?: ReactNode;
}

export default function DeferredMount({ children, fallback = null }: DeferredMountProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const schedule =
      window.requestIdleCallback ??
      ((callback: () => void) => {
        window.setTimeout(callback, 1);
      });

    const handle = schedule(() => {
      setMounted(true);
    });

    return () => {
      if (typeof handle === 'number' && window.cancelIdleCallback) {
        window.cancelIdleCallback(handle);
      }
    };
  }, []);

  return mounted ? children : fallback;
}
