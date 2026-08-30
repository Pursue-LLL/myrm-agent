/**
 * [INPUT]
 * - react::memo, type ReactNode
 * - ./types::ExtensionSlotName, ExtensionSlotContext
 * - ./useExtensionSlotStore::useExtensionSlotStore
 * - @/lib/utils/classnameUtils::cn
 *
 * [OUTPUT]
 * - ExtensionSlot: 声明式插槽挂载容器组件
 *
 * [POS]
 * 声明式扩展插槽挂载容器。按指定 slotName 查询当前已注册且满足 condition 的扩展项，
 * 依次进行渲染；若无匹配项则展示可选的 fallback。
 */

'use client';

import { memo, type ReactNode } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useExtensionSlotStore } from './useExtensionSlotStore';
import type { ExtensionSlotContext, ExtensionSlotName } from './types';
import { cn } from '@/lib/utils/classnameUtils';

interface ExtensionSlotProps {
  name: ExtensionSlotName;
  className?: string;
  context?: ExtensionSlotContext;
  fallback?: ReactNode;
}

export const ExtensionSlot = memo<ExtensionSlotProps>(({ name, className, context, fallback = null }) => {
  const contributions = useExtensionSlotStore(
    useShallow((state) =>
      state.contributions.filter((c) => c.slotName === name).sort((a, b) => (a.order ?? 100) - (b.order ?? 100)),
    ),
  );

  const activeContributions = contributions.filter((contrib) => {
    if (!contrib.condition) {
      return true;
    }
    try {
      return contrib.condition(context);
    } catch {
      return false;
    }
  });

  if (activeContributions.length === 0) {
    return fallback ? <>{fallback}</> : null;
  }

  return (
    <div className={cn('extension-slot', className)} data-slot-name={name}>
      {activeContributions.map((contrib) => {
        const Component = contrib.component;
        return <Component key={contrib.id} context={context} />;
      })}
    </div>
  );
});

ExtensionSlot.displayName = 'ExtensionSlot';
