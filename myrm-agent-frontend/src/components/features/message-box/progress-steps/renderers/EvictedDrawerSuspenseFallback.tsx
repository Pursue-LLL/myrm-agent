'use client';

import React from 'react';

/** Lightweight Suspense fallback while EvictedOutputDrawer lazy chunk loads. */
export const EvictedDrawerSuspenseFallback: React.FC = () => (
  <div
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    aria-hidden
  >
    <div
      className={[
        'flex items-center justify-center',
        'w-[min(90vw,100%)] sm:w-[90vw] max-w-5xl h-[min(80vh,100%)] sm:h-[80vh]',
        'bg-zinc-950 border border-zinc-800 rounded-2xl',
      ].join(' ')}
    >
      <div className="w-4 h-4 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin" />
    </div>
  </div>
);

export default EvictedDrawerSuspenseFallback;
