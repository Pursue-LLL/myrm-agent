'use client';

import { useEffect, useState } from 'react';
import {
  type AllowAlwaysDuration,
  type AllowAlwaysScope,
  defaultAllowAlwaysScope,
} from '@/lib/approval/allowAlwaysScope';

/** The scope and duration picked for a standing "always allow"; the scope returns to the tool's default for each approval. */
export function useAllowAlwaysChoice(approvalId: string, toolName: string) {
  const [scope, setScope] = useState<AllowAlwaysScope>(() => defaultAllowAlwaysScope(toolName));
  const [duration, setDuration] = useState<AllowAlwaysDuration>('session');

  useEffect(() => {
    setScope(defaultAllowAlwaysScope(toolName));
  }, [approvalId, toolName]);

  return { scope, setScope, duration, setDuration };
}
