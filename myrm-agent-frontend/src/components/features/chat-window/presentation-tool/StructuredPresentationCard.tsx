import React from 'react';
import {
  Calendar,
  Check,
  Compass,
  Layers,
  ShoppingBag,
  Sparkles,
} from 'lucide-react';
import {
  ItineraryStepItem,
  PresentationItem,
  PresentationPayload,
  ProductPresentationItem,
} from './presentationToolTypes';
import { usePresentationToolStore } from './usePresentationToolStore';

interface StructuredPresentationCardProps {
  presentation: PresentationPayload;
  onItemSelected?: (item: PresentationItem) => void;
  className?: string;
}

function renderToolIcon(toolName: string) {
  if (toolName === 'present_products') {
    return <ShoppingBag className="h-4 w-4 text-emerald-500" />;
  }
  if (toolName === 'present_itinerary') {
    return <Calendar className="h-4 w-4 text-blue-500" />;
  }
  return <Layers className="h-4 w-4 text-purple-500" />;
}

export const StructuredPresentationCard: React.FC<
  StructuredPresentationCardProps
> = ({ presentation, onItemSelected, className = '' }) => {
  const selectedPositional = usePresentationToolStore(
    (state) => state.selectedPositionalItem,
  );

  const isSelected = (item: PresentationItem) => {
    return (
      selectedPositional?.presentationId === presentation.id &&
      selectedPositional?.item.position === item.position
    );
  };

  const handleItemClick = (item: PresentationItem) => {
    if (onItemSelected) {
      onItemSelected(item);
    }
  };

  return (
    <div
      data-testid={`structured-presentation-card-${presentation.id}`}
      className={`my-3 w-full max-w-xl rounded-xl border border-primary/25 bg-background/95 p-4 text-xs shadow-md backdrop-blur-md dark:bg-muted/30 ${className}`}
    >
      {/* 头部标题与结构化契约微标 */}
      <div className="flex items-start justify-between gap-2 border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
            {renderToolIcon(presentation.toolName)}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-foreground text-sm">
                {presentation.title}
              </span>
              <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                展示工具原生契约
              </span>
            </div>
            {presentation.description && (
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {presentation.description}
              </p>
            )}
          </div>
        </div>

        <span className="font-mono text-[10px] text-muted-foreground">
          {presentation.items.length} 项
        </span>
      </div>

      {/* 结构化条目列表 */}
      <div className="mt-3 space-y-2">
        {presentation.items.map((item) => {
          const selected = isSelected(item);

          return (
            <button
              key={`${presentation.id}-${item.position}`}
              type="button"
              onClick={() => {
                handleItemClick(item);
              }}
              className={`flex w-full cursor-pointer items-start justify-between gap-3 rounded-lg border p-2.5 text-left transition-all ${
                selected
                  ? 'border-primary bg-primary/10 ring-1 ring-primary shadow-xs'
                  : 'border-border/60 bg-background/60 hover:bg-muted/40'
              }`}
            >
              <div className="flex items-start gap-2.5">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary">
                  {item.position}
                </span>

                <div>
                  {'title' in item && (
                    <span className="font-medium text-foreground text-xs">
                      {item.title}
                    </span>
                  )}
                  {'subtitle' in item && item.subtitle && (
                    <p className="text-[11px] text-muted-foreground">
                      {item.subtitle}
                    </p>
                  )}
                  {'description' in item && item.description && (
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {item.description}
                    </p>
                  )}
                  {'highlight' in item && item.highlight && (
                    <span className="mt-1 inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.2 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                      <Sparkles className="h-2.5 w-2.5" />
                      <span>{item.highlight}</span>
                    </span>
                  )}
                </div>
              </div>

              {selected && (
                <div className="flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground shadow-2xs">
                  <Check className="h-2.5 w-2.5" />
                  <span>已选中指代</span>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
