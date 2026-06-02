'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Trash2, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { ProviderConfig } from '@/store/config/providerTypes';
import ProviderIcon from './ProviderIcon';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface ProviderListProps {
  providers: ProviderConfig[];
  selectedId: string;
  onSelect: (id: string) => void;
  onAddProvider: () => void;
  onRemoveProvider: (id: string) => void;
  onReorderProviders?: (providers: ProviderConfig[]) => void;
}

// 可拖拽的提供商项
const SortableProviderItem = memo<{
  provider: ProviderConfig;
  isSelected: boolean;
  onSelect: () => void;
  onRemove: () => void;
  t: ReturnType<typeof useTranslations<'settings.modelService'>>;
}>(({ provider, isSelected, onSelect, onRemove, t }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: provider.id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer transition-all duration-200',
        isSelected
          ? 'bg-accent-warm/10 border border-accent-warm/30 shadow-[var(--shadow-brand)]'
          : 'hover:bg-accent/50 border border-transparent',
        isDragging && 'opacity-50 shadow-lg z-50',
      )}
      onClick={() => {
        onSelect();
      }}
      role="button"
      aria-label={provider.name}
    >
      <div className="flex items-center gap-2 min-w-0">
        {/* 拖拽手柄 */}
        <div
          {...attributes}
          {...listeners}
          className="p-0.5 cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground"
          // onClick={(e) => e.stopPropagation()} // Removed to fix E2E click
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </div>
        <ProviderIcon providerId={provider.id} providerName={provider.name} size={18} />
        <span className={cn('text-sm font-medium truncate', isSelected ? 'text-accent-warm' : 'text-foreground')}>
          {provider.name}
        </span>
      </div>

      <div className="flex items-center gap-2">
        {/* 绿色圆点表示已启用/可用 */}
        {provider.isEnabled && <div className="w-2 h-2 rounded-full bg-green-500 shadow-green-500/50" />}
        {!provider.isBuiltIn && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="opacity-0 group-hover:opacity-100 p-1 hover:bg-destructive/10 rounded transition-all"
            title={t('removeProvider')}
          >
            <Trash2 className="w-3.5 h-3.5 text-destructive" />
          </button>
        )}
      </div>
    </div>
  );
});

SortableProviderItem.displayName = 'SortableProviderItem';

const ProviderList = memo<ProviderListProps>(
  ({ providers, selectedId, onSelect, onAddProvider, onRemoveProvider, onReorderProviders }) => {
    const t = useTranslations('settings.modelService');

    const sensors = useSensors(
      useSensor(PointerSensor, {
        activationConstraint: {
          distance: 8,
        },
      }),
      useSensor(KeyboardSensor, {
        coordinateGetter: sortableKeyboardCoordinates,
      }),
    );

    const handleDragEnd = (event: DragEndEvent) => {
      const { active, over } = event;

      if (over && active.id !== over.id) {
        const oldIndex = providers.findIndex((p) => p.id === active.id);
        const newIndex = providers.findIndex((p) => p.id === over.id);

        const reordered = arrayMove(providers, oldIndex, newIndex);
        onReorderProviders?.(reordered);
      }
    };

    return (
      <div className="flex flex-col">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={providers.map((p) => p.id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-1">
              {providers.map((provider) => (
                <SortableProviderItem
                  key={provider.id}
                  provider={provider}
                  isSelected={selectedId === provider.id}
                  onSelect={() => onSelect(provider.id)}
                  onRemove={() => onRemoveProvider(provider.id)}
                  t={t}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>

        {/* 添加提供商按钮 */}
        <TooltipProvider delayDuration={300}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onAddProvider}
                className="flex items-center gap-2 px-3 py-2.5 mt-2 rounded-lg border-2 border-dashed border-border/80 hover:border-accent-warm/60 hover:bg-accent-warm/5 transition-colors"
              >
                <Plus className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">{t('addProvider')}</span>
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-64 text-xs">
              {t('customProviderNotice')}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    );
  },
);

ProviderList.displayName = 'ProviderList';

export default ProviderList;
