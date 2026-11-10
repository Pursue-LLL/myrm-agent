'use client';

import { useEffect, useState, type ReactNode } from 'react';

import { scheduleWhenIdle } from '@/lib/utils/scheduleWhenIdle';

interface DeferredMountProps {
  children: ReactNode;
  fallback?: ReactNode;
}

export default function DeferredMount({ children, fallback = null }: DeferredMountProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => scheduleWhenIdle(() => setMounted(true)), []);

  return mounted ? children : fallback;
}
