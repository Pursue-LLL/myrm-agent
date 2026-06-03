'use client';

import { memo, useRef, useEffect, useState } from 'react';
import { useWindowVirtualizer } from '@tanstack/react-virtual';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { Skeleton } from '@/components/primitives/skeleton';
import SkillCard from './SkillCard';
import SkillEmptyState from './SkillEmptyState';
import type { Skill, SkillLifecycleAction } from '@/store/skill/types';

interface SkillListProps {
  skills: Skill[];
  isSkillEnabled: (skillId: string) => boolean;
  isLoading: boolean;
  emptyStateType: 'market' | 'personal' | 'local' | 'enabled' | 'search';
  showDeleteButton?: boolean;
  onToggle: (skillId: string) => void;
  onViewDetails: (skill: Skill) => void;
  onDelete?: (skill: Skill) => void;
  onUpload?: () => void;
  onLifecycleAction?: (skill: Skill, action: SkillLifecycleAction) => void;
  onManageInstances?: (skillName: string) => void;
}

// 骨架屏组件
const SkillCardSkeleton = memo(() => (
  <div className="rounded-xl border bg-card p-4">
    <div className="flex items-start gap-3">
      <Skeleton className="w-10 h-10 rounded-lg" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      <Skeleton className="w-10 h-5 rounded-full" />
    </div>
    <div className="mt-4 flex items-center gap-2">
      <Skeleton className="h-5 w-16 rounded-full" />
      <Skeleton className="h-5 w-12 rounded-full" />
      <Skeleton className="h-5 w-14 rounded-full" />
    </div>
  </div>
));

SkillCardSkeleton.displayName = 'SkillCardSkeleton';

const SkillList = memo(
  ({
    skills,
    isSkillEnabled,
    isLoading,
    emptyStateType,
    showDeleteButton = false,
    onToggle,
    onViewDetails,
    onDelete,
    onUpload,
    onLifecycleAction,
    onManageInstances,
  }: SkillListProps) => {
    // 加载状态
    if (isLoading) {
      return (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkillCardSkeleton key={i} />
          ))}
        </div>
      );
    }

    // 空状态
    if (skills.length === 0) {
      return <SkillEmptyState type={emptyStateType} onUpload={onUpload} />;
    }

    // 技能列表虚拟滚动
    const parentRef = useRef<HTMLDivElement>(null);
    const isXl = useMediaQuery('(min-width: 1280px)');
    const isMd = useMediaQuery('(min-width: 768px)');

    // Server-side rendering compatibility
    const [isMounted, setIsMounted] = useState(false);
    useEffect(() => {
      setIsMounted(true);
    }, []);

    const columns = isMounted ? (isXl ? 3 : isMd ? 2 : 1) : 1;
    const rowCount = Math.ceil(skills.length / columns);

    const virtualizer = useWindowVirtualizer({
      count: rowCount,
      estimateSize: () => 200, // estimated height of a skill card + gap
      overscan: 3,
    });

    return (
      <div ref={parentRef} style={{ width: '100%' }}>
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const startIndex = virtualRow.index * columns;
            const rowSkills = skills.slice(startIndex, startIndex + columns);

            return (
              <div
                key={virtualRow.key}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
                className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 pb-4"
              >
                {rowSkills.map((skill) => (
                  <SkillCard
                    key={skill.id}
                    skill={skill}
                    isEnabled={isSkillEnabled(skill.id)}
                    showDeleteButton={showDeleteButton}
                    onToggle={onToggle}
                    onViewDetails={onViewDetails}
                    onDelete={onDelete}
                    onLifecycleAction={onLifecycleAction}
                    onManageInstances={onManageInstances}
                  />
                ))}
              </div>
            );
          })}
        </div>
      </div>
    );
  },
);

SkillList.displayName = 'SkillList';

export default SkillList;
