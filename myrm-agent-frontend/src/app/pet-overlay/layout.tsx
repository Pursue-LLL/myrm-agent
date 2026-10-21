'use client';

import { useEffect } from 'react';

export default function PetOverlayLayout({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    document.documentElement.style.background = 'transparent';
    document.body.style.background = 'transparent';
    return () => {
      document.documentElement.style.background = '';
      document.body.style.background = '';
    };
  }, []);

  return <div className="h-screen w-screen overflow-hidden bg-transparent">{children}</div>;
}
