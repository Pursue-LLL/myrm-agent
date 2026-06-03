'use client';

import { useEffect, useState } from 'react';
import type mermaid from 'mermaid';

type MermaidLib = typeof mermaid;

export function useLazyMermaid() {
  const [mermaidLib, setMermaidLib] = useState<MermaidLib | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    import('mermaid')
      .then((mod) => {
        if (mounted) {
          setMermaidLib(() => mod.default);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error('Failed to load mermaid:', err);
        if (mounted) {
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  return { mermaidLib, loading };
}
