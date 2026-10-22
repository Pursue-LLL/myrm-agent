'use client';

/**
 * Rotating Goal-Oriented Composer Placeholder Engine Hook.
 * Automatically rotates high-leverage mission templates to reduce cold-start friction.
 */

import { useCallback, useEffect, useState } from 'react';
import { RotatingPlaceholderEntry } from './globalCommandPaletteTypes';

export const DEFAULT_TASK_TEMPLATES: readonly RotatingPlaceholderEntry[] = [
  {
    id: 'tpl_code_refactor',
    category: 'Architecture',
    prompt: 'Refactor complex modules to eliminate Any types and stay under 400 lines...',
  },
  {
    id: 'tpl_test_suite',
    category: 'Quality',
    prompt: 'Generate an end-to-end regression test suite with 100% green coverage...',
  },
  {
    id: 'tpl_financial_analysis',
    category: 'Analysis',
    prompt: 'Analyze and cross-compare two quarterly financial reports into markdown tables...',
  },
  {
    id: 'tpl_mermaid_flow',
    category: 'Design',
    prompt: 'Convert this architecture design RFC into interactive Mermaid sequence diagrams...',
  },
  {
    id: 'tpl_api_audit',
    category: 'Security',
    prompt: 'Audit REST endpoints for authorization vulnerabilities and rate limit leaks...',
  },
] as const;

interface UseRotatingPlaceholderOptions {
  intervalMs?: number;
  templates?: readonly RotatingPlaceholderEntry[];
  enabled?: boolean;
}

export interface UseRotatingPlaceholderReturn {
  currentEntry: RotatingPlaceholderEntry;
  placeholderText: string;
  category: string;
  currentIndex: number;
  nextPlaceholder: () => void;
}

export function useRotatingPlaceholder(
  options: UseRotatingPlaceholderOptions = {}
): UseRotatingPlaceholderReturn {
  const {
    intervalMs = 4500,
    templates = DEFAULT_TASK_TEMPLATES,
    enabled = true,
  } = options;

  const [currentIndex, setCurrentIndex] = useState<number>(0);

  const nextPlaceholder = useCallback(() => {
    setCurrentIndex((prev) => (templates.length > 0 ? (prev + 1) % templates.length : 0));
  }, [templates.length]);

  useEffect(() => {
    if (!enabled || templates.length <= 1) {
      return;
    }

    const timer = setInterval(() => {
      nextPlaceholder();
    }, intervalMs);

    return () => {
      clearInterval(timer);
    };
  }, [enabled, intervalMs, templates.length, nextPlaceholder]);

  const currentEntry = templates[currentIndex] || templates[0];

  return {
    currentEntry,
    placeholderText: currentEntry.prompt,
    category: currentEntry.category,
    currentIndex,
    nextPlaceholder,
  };
}
